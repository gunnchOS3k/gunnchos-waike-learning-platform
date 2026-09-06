//! Native offline store: cached lease + durable sync outbox inside the encrypted DB.
//!
//! Invariants enforced here rather than in the UI layer:
//!
//! * A mutation may only reach `acknowledged` through [`EncryptedDb::persist_sync_ack`],
//!   which requires a non-empty server receipt. No other path can set that status.
//! * Every write is followed by re-encrypting the envelope, so an app kill between two
//!   commands cannot lose queued work.
//! * Callers pass typed values only. There is no command that accepts SQL.

use crate::db::EncryptedDb;
use crate::error::AppError;
use chrono::{DateTime, Utc};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};

/// The only statuses a mutation row may hold.
pub const SYNC_STATUSES: &[&str] = &[
    "pending",
    "syncing",
    "acknowledged",
    "conflict",
    "rejected",
    "retryable_error",
    "quarantined",
];

/// Statuses a caller may set directly. `acknowledged` is deliberately excluded.
pub const CLIENT_SETTABLE_STATUSES: &[&str] = &[
    "pending",
    "syncing",
    "conflict",
    "rejected",
    "retryable_error",
    "quarantined",
];

/// Work that still needs to reach the server.
pub const OUTSTANDING_STATUSES: &[&str] = &["pending", "syncing", "retryable_error"];

pub const MIGRATION_SQL: &str = "
CREATE TABLE IF NOT EXISTS sync_outbox (
    client_mutation_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL DEFAULT '',
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    base_revision INTEGER NOT NULL DEFAULT 0,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    local_sequence INTEGER NOT NULL,
    sync_status TEXT NOT NULL CHECK (sync_status IN (
      'pending','syncing','acknowledged','conflict','rejected','retryable_error','quarantined'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    ack_receipt_json TEXT,
    ack_persisted_at TEXT,
    CHECK (sync_status <> 'acknowledged' OR (ack_receipt_json IS NOT NULL AND ack_persisted_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_status ON sync_outbox(sync_status, local_sequence);

CREATE TABLE IF NOT EXISTS offline_lease_cache (
    lease_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    site_id TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL,
    device_id TEXT NOT NULL DEFAULT '',
    issued_at TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0,1)),
    revoke_reason TEXT,
    cached_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_offline_lease_section ON offline_lease_cache(section_id);
";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CachedLease {
    pub lease_id: String,
    pub user_id: String,
    pub site_id: String,
    pub section_id: String,
    pub device_id: String,
    pub issued_at: String,
    pub expires_at: String,
    pub capabilities: Vec<String>,
    pub revoked: bool,
    pub revoke_reason: Option<String>,
}

impl CachedLease {
    /// Usable for offline work: not revoked and not past its server-issued expiry.
    pub fn is_usable_at(&self, now: DateTime<Utc>) -> bool {
        if self.revoked {
            return false;
        }
        match DateTime::parse_from_rfc3339(&self.expires_at) {
            Ok(exp) => exp.with_timezone(&Utc) > now,
            // An unparseable expiry is treated as expired rather than trusted.
            Err(_) => false,
        }
    }

    pub fn allows(&self, capability: &str) -> bool {
        self.capabilities.iter().any(|c| c == capability)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SyncOutboxItem {
    pub client_mutation_id: String,
    #[serde(default)]
    pub section_id: String,
    pub entity_type: String,
    pub entity_id: String,
    #[serde(default)]
    pub base_revision: i64,
    pub operation: String,
    pub payload_json: String,
    pub local_sequence: i64,
    pub sync_status: String,
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub attempt_count: i64,
    #[serde(default)]
    pub last_error: Option<String>,
    #[serde(default)]
    pub ack_receipt_json: Option<String>,
    #[serde(default)]
    pub ack_persisted_at: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct SyncCounts {
    pub pending: i64,
    pub syncing: i64,
    pub acknowledged: i64,
    pub conflict: i64,
    pub rejected: i64,
    pub retryable_error: i64,
    pub quarantined: i64,
    /// Rows whose ack receipt is durably stored locally.
    pub ack_persisted: i64,
    /// Must always be zero; a non-zero value means the ack invariant was violated.
    pub acknowledged_without_receipt: i64,
}

impl SyncCounts {
    pub fn outstanding(&self) -> i64 {
        OUTSTANDING_STATUSES
            .iter()
            .map(|s| match *s {
                "pending" => self.pending,
                "syncing" => self.syncing,
                "retryable_error" => self.retryable_error,
                _ => 0,
            })
            .sum()
    }

    /// Anything the learner must look at before the work is really "in".
    pub fn needs_attention(&self) -> i64 {
        self.conflict + self.rejected + self.quarantined
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OfflineState {
    pub counts: SyncCounts,
    pub lease: Option<CachedLease>,
    pub lease_usable: bool,
    pub outstanding: i64,
    pub needs_attention: i64,
    /// True only when nothing is outstanding and every ack is durably persisted.
    pub all_work_acknowledged: bool,
}

fn validate_status(status: &str, allowed: &[&str]) -> Result<(), AppError> {
    if allowed.contains(&status) {
        Ok(())
    } else {
        Err(AppError::Db(format!("invalid sync status: {status}")))
    }
}

pub(crate) fn ensure_column(
    conn: &Connection,
    table: &str,
    column: &str,
    decl: &str,
) -> Result<(), AppError> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let mut found = false;
    let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
    for r in rows {
        if r? == column {
            found = true;
            break;
        }
    }
    if !found {
        conn.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {column} {decl};"))?;
    }
    Ok(())
}

/// Bring pre-existing local databases up to the current offline schema.
pub(crate) fn upgrade_schema(conn: &Connection) -> Result<(), AppError> {
    for (column, decl) in [
        ("section_id", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_error", "TEXT"),
    ] {
        ensure_column(conn, "sync_outbox", column, decl)?;
    }
    for (column, decl) in [
        ("user_id", "TEXT NOT NULL DEFAULT ''"),
        ("site_id", "TEXT NOT NULL DEFAULT ''"),
        ("device_id", "TEXT NOT NULL DEFAULT ''"),
        ("issued_at", "TEXT NOT NULL DEFAULT ''"),
        ("revoke_reason", "TEXT"),
        ("cached_at", "TEXT NOT NULL DEFAULT ''"),
    ] {
        ensure_column(conn, "offline_lease_cache", column, decl)?;
    }
    Ok(())
}

impl EncryptedDb {
    // --- lease cache ---------------------------------------------------------

    pub fn cache_lease(&self, lease: &CachedLease, cached_at: &str) -> Result<(), AppError> {
        if lease.lease_id.trim().is_empty() || lease.section_id.trim().is_empty() {
            return Err(AppError::Db("lease requires lease_id and section_id".into()));
        }
        let caps = serde_json::to_string(&lease.capabilities)?;
        self.conn.execute(
            "INSERT INTO offline_lease_cache(
                lease_id, user_id, site_id, section_id, device_id, issued_at, expires_at,
                capabilities_json, revoked, revoke_reason, cached_at
             ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)
             ON CONFLICT(lease_id) DO UPDATE SET
                user_id=excluded.user_id,
                site_id=excluded.site_id,
                section_id=excluded.section_id,
                device_id=excluded.device_id,
                issued_at=excluded.issued_at,
                expires_at=excluded.expires_at,
                capabilities_json=excluded.capabilities_json,
                revoked=excluded.revoked,
                revoke_reason=excluded.revoke_reason,
                cached_at=excluded.cached_at",
            rusqlite::params![
                lease.lease_id,
                lease.user_id,
                lease.site_id,
                lease.section_id,
                lease.device_id,
                lease.issued_at,
                lease.expires_at,
                caps,
                i64::from(lease.revoked),
                lease.revoke_reason,
                cached_at,
            ],
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    fn map_lease(row: &rusqlite::Row<'_>) -> rusqlite::Result<CachedLease> {
        let caps_json: String = row.get(7)?;
        Ok(CachedLease {
            lease_id: row.get(0)?,
            user_id: row.get(1)?,
            site_id: row.get(2)?,
            section_id: row.get(3)?,
            device_id: row.get(4)?,
            issued_at: row.get(5)?,
            expires_at: row.get(6)?,
            capabilities: serde_json::from_str(&caps_json).unwrap_or_default(),
            revoked: row.get::<_, i64>(8)? == 1,
            revoke_reason: row.get(9)?,
        })
    }

    const LEASE_COLUMNS: &'static str = "lease_id, user_id, site_id, section_id, device_id, \
         issued_at, expires_at, capabilities_json, revoked, revoke_reason";

    pub fn get_lease(&self, lease_id: &str) -> Result<Option<CachedLease>, AppError> {
        let sql = format!(
            "SELECT {} FROM offline_lease_cache WHERE lease_id=?1",
            Self::LEASE_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let mut rows = stmt.query([lease_id])?;
        match rows.next()? {
            Some(row) => Ok(Some(Self::map_lease(row)?)),
            None => Ok(None),
        }
    }

    /// Most recently cached lease for a section, regardless of usability.
    pub fn get_section_lease(&self, section_id: &str) -> Result<Option<CachedLease>, AppError> {
        let sql = format!(
            "SELECT {} FROM offline_lease_cache WHERE section_id=?1 \
             ORDER BY revoked ASC, expires_at DESC LIMIT 1",
            Self::LEASE_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let mut rows = stmt.query([section_id])?;
        match rows.next()? {
            Some(row) => Ok(Some(Self::map_lease(row)?)),
            None => Ok(None),
        }
    }

    pub fn list_leases(&self) -> Result<Vec<CachedLease>, AppError> {
        let sql = format!(
            "SELECT {} FROM offline_lease_cache ORDER BY section_id, expires_at DESC",
            Self::LEASE_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt.query_map([], Self::map_lease)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn mark_lease_revoked(&self, lease_id: &str, reason: &str) -> Result<(), AppError> {
        let changed = self.conn.execute(
            "UPDATE offline_lease_cache SET revoked=1, revoke_reason=?2 WHERE lease_id=?1",
            rusqlite::params![lease_id, reason],
        )?;
        if changed == 0 {
            return Err(AppError::NotFound(format!("lease {lease_id}")));
        }
        self.persist_envelope()?;
        Ok(())
    }

    /// Force a cached lease past its expiry (server said so, or local clock proved it).
    pub fn mark_lease_expired(&self, lease_id: &str, expired_at: &str) -> Result<(), AppError> {
        let changed = self.conn.execute(
            "UPDATE offline_lease_cache SET expires_at=?2 WHERE lease_id=?1",
            rusqlite::params![lease_id, expired_at],
        )?;
        if changed == 0 {
            return Err(AppError::NotFound(format!("lease {lease_id}")));
        }
        self.persist_envelope()?;
        Ok(())
    }

    pub fn delete_lease(&self, lease_id: &str) -> Result<(), AppError> {
        self.conn
            .execute("DELETE FROM offline_lease_cache WHERE lease_id=?1", [lease_id])?;
        self.persist_envelope()?;
        Ok(())
    }

    // --- sync outbox ---------------------------------------------------------

    pub fn enqueue_sync_mutation(&self, item: &SyncOutboxItem) -> Result<(), AppError> {
        validate_status(&item.sync_status, CLIENT_SETTABLE_STATUSES)?;
        if item.client_mutation_id.trim().len() < 8 {
            return Err(AppError::Db("client_mutation_id too short".into()));
        }
        self.conn.execute(
            "INSERT INTO sync_outbox(
                client_mutation_id, section_id, entity_type, entity_id, base_revision, operation,
                payload_json, local_sequence, sync_status, created_at, updated_at, attempt_count,
                last_error, ack_receipt_json, ack_persisted_at
             ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15)",
            rusqlite::params![
                item.client_mutation_id,
                item.section_id,
                item.entity_type,
                item.entity_id,
                item.base_revision,
                item.operation,
                item.payload_json,
                item.local_sequence,
                item.sync_status,
                item.created_at,
                if item.updated_at.is_empty() {
                    item.created_at.clone()
                } else {
                    item.updated_at.clone()
                },
                item.attempt_count,
                item.last_error,
                item.ack_receipt_json,
                item.ack_persisted_at,
            ],
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    pub fn next_local_sequence(&self) -> Result<i64, AppError> {
        let mut stmt = self
            .conn
            .prepare("SELECT COALESCE(MAX(local_sequence), 0) + 1 FROM sync_outbox")?;
        let mut rows = stmt.query([])?;
        match rows.next()? {
            Some(row) => Ok(row.get(0)?),
            None => Ok(1),
        }
    }

    fn map_outbox(row: &rusqlite::Row<'_>) -> rusqlite::Result<SyncOutboxItem> {
        Ok(SyncOutboxItem {
            client_mutation_id: row.get(0)?,
            section_id: row.get(1)?,
            entity_type: row.get(2)?,
            entity_id: row.get(3)?,
            base_revision: row.get(4)?,
            operation: row.get(5)?,
            payload_json: row.get(6)?,
            local_sequence: row.get(7)?,
            sync_status: row.get(8)?,
            created_at: row.get(9)?,
            updated_at: row.get(10)?,
            attempt_count: row.get(11)?,
            last_error: row.get(12)?,
            ack_receipt_json: row.get(13)?,
            ack_persisted_at: row.get(14)?,
        })
    }

    const OUTBOX_COLUMNS: &'static str =
        "client_mutation_id, section_id, entity_type, entity_id, base_revision, operation, \
         payload_json, local_sequence, sync_status, created_at, updated_at, attempt_count, \
         last_error, ack_receipt_json, ack_persisted_at";

    /// Everything that has not reached the server yet, oldest first.
    pub fn list_pending_sync(&self) -> Result<Vec<SyncOutboxItem>, AppError> {
        let sql = format!(
            "SELECT {} FROM sync_outbox
             WHERE sync_status IN ('pending','syncing','retryable_error')
             ORDER BY local_sequence ASC",
            Self::OUTBOX_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt.query_map([], Self::map_outbox)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn list_sync_by_status(&self, status: &str) -> Result<Vec<SyncOutboxItem>, AppError> {
        validate_status(status, SYNC_STATUSES)?;
        let sql = format!(
            "SELECT {} FROM sync_outbox WHERE sync_status=?1 ORDER BY local_sequence ASC",
            Self::OUTBOX_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt.query_map([status], Self::map_outbox)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn get_sync_mutation(&self, id: &str) -> Result<Option<SyncOutboxItem>, AppError> {
        let sql = format!(
            "SELECT {} FROM sync_outbox WHERE client_mutation_id=?1",
            Self::OUTBOX_COLUMNS
        );
        let mut stmt = self.conn.prepare(&sql)?;
        let mut rows = stmt.query([id])?;
        match rows.next()? {
            Some(row) => Ok(Some(Self::map_outbox(row)?)),
            None => Ok(None),
        }
    }

    /// Move a mutation between non-acknowledged states. Reaching `acknowledged`
    /// requires [`Self::persist_sync_ack`] and a server receipt.
    pub fn update_mutation_state(
        &self,
        client_mutation_id: &str,
        status: &str,
        last_error: Option<&str>,
        updated_at: &str,
    ) -> Result<(), AppError> {
        validate_status(status, CLIENT_SETTABLE_STATUSES)?;
        let existing = self
            .get_sync_mutation(client_mutation_id)?
            .ok_or_else(|| AppError::NotFound(format!("mutation {client_mutation_id}")))?;
        if existing.sync_status == "acknowledged" {
            return Err(AppError::Db(
                "acknowledged mutations are terminal and cannot be reopened".into(),
            ));
        }
        let increment = i64::from(status == "syncing");
        self.conn.execute(
            "UPDATE sync_outbox
             SET sync_status=?2, last_error=?3, updated_at=?4, attempt_count=attempt_count+?5
             WHERE client_mutation_id=?1",
            rusqlite::params![client_mutation_id, status, last_error, updated_at, increment],
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    /// Persist durable ack before clearing pending — never mark acknowledged without receipt JSON.
    pub fn persist_sync_ack(
        &self,
        client_mutation_id: &str,
        receipt_json: &str,
        ack_persisted_at: &str,
    ) -> Result<(), AppError> {
        if receipt_json.trim().is_empty() {
            return Err(AppError::Db("ack requires durable receipt".into()));
        }
        if serde_json::from_str::<serde_json::Value>(receipt_json).is_err() {
            return Err(AppError::Db("ack receipt must be valid JSON".into()));
        }
        if ack_persisted_at.trim().is_empty() {
            return Err(AppError::Db("ack requires a persistence timestamp".into()));
        }
        if self.get_sync_mutation(client_mutation_id)?.is_none() {
            return Err(AppError::NotFound(format!("mutation {client_mutation_id}")));
        }
        self.conn.execute(
            "UPDATE sync_outbox
             SET sync_status='acknowledged', ack_receipt_json=?1, ack_persisted_at=?2,
                 updated_at=?2, last_error=NULL
             WHERE client_mutation_id=?3",
            rusqlite::params![receipt_json, ack_persisted_at, client_mutation_id],
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    pub fn get_sync_counts(&self) -> Result<SyncCounts, AppError> {
        let mut counts = SyncCounts::default();
        let mut stmt = self
            .conn
            .prepare("SELECT sync_status, COUNT(*) FROM sync_outbox GROUP BY sync_status")?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })?;
        for r in rows {
            let (status, n) = r?;
            match status.as_str() {
                "pending" => counts.pending = n,
                "syncing" => counts.syncing = n,
                "acknowledged" => counts.acknowledged = n,
                "conflict" => counts.conflict = n,
                "rejected" => counts.rejected = n,
                "retryable_error" => counts.retryable_error = n,
                "quarantined" => counts.quarantined = n,
                _ => {}
            }
        }
        counts.ack_persisted = self.conn.query_row(
            "SELECT COUNT(*) FROM sync_outbox
             WHERE sync_status='acknowledged' AND ack_receipt_json IS NOT NULL
               AND ack_persisted_at IS NOT NULL",
            [],
            |row| row.get(0),
        )?;
        counts.acknowledged_without_receipt = self.conn.query_row(
            "SELECT COUNT(*) FROM sync_outbox
             WHERE sync_status='acknowledged'
               AND (ack_receipt_json IS NULL OR ack_persisted_at IS NULL)",
            [],
            |row| row.get(0),
        )?;
        Ok(counts)
    }

    pub fn offline_state(
        &self,
        section_id: Option<&str>,
        now: DateTime<Utc>,
    ) -> Result<OfflineState, AppError> {
        let counts = self.get_sync_counts()?;
        let lease = match section_id {
            Some(sid) => self.get_section_lease(sid)?,
            None => self.list_leases()?.into_iter().next(),
        };
        let lease_usable = lease.as_ref().map(|l| l.is_usable_at(now)).unwrap_or(false);
        let outstanding = counts.outstanding();
        let needs_attention = counts.needs_attention();
        Ok(OfflineState {
            all_work_acknowledged: outstanding == 0
                && needs_attention == 0
                && counts.acknowledged_without_receipt == 0
                && counts.acknowledged == counts.ack_persisted,
            counts,
            lease,
            lease_usable,
            outstanding,
            needs_attention,
        })
    }
}
