//! Native offline wiring tests against the real encrypted database.

use crate::db::EncryptedDb;
use crate::offline::{CachedLease, SyncOutboxItem};
use chrono::{DateTime, Utc};
use tempfile::tempdir;

const KEY: [u8; 32] = [11u8; 32];

fn ts(s: &str) -> DateTime<Utc> {
    DateTime::parse_from_rfc3339(s).unwrap().with_timezone(&Utc)
}

fn lease(section: &str, expires: &str) -> CachedLease {
    CachedLease {
        lease_id: format!("lease_{section}"),
        user_id: "learner-alpha".into(),
        site_id: "site-alpha".into(),
        section_id: section.into(),
        device_id: "device-a".into(),
        issued_at: "2024-01-01T00:00:00Z".into(),
        expires_at: expires.into(),
        capabilities: vec!["lesson_progress".into(), "quiz_attempt".into()],
        revoked: false,
        revoke_reason: None,
    }
}

fn item(id: &str, seq: i64) -> SyncOutboxItem {
    SyncOutboxItem {
        client_mutation_id: id.into(),
        section_id: "sec_alpha_dc_w01".into(),
        entity_type: "lesson_progress".into(),
        entity_id: "L1".into(),
        base_revision: 0,
        operation: "upsert".into(),
        payload_json: "{\"percent_complete\":40}".into(),
        local_sequence: seq,
        sync_status: "pending".into(),
        created_at: "2024-01-01T00:00:00Z".into(),
        updated_at: "2024-01-01T00:00:00Z".into(),
        attempt_count: 0,
        last_error: None,
        ack_receipt_json: None,
        ack_persisted_at: None,
    }
}

#[test]
fn ack_requires_a_durable_receipt() {
    let dir = tempdir().unwrap();
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();
    db.enqueue_sync_mutation(&item("mut_rust_ack_1", 1)).unwrap();
    assert_eq!(db.list_pending_sync().unwrap().len(), 1);

    assert!(db.persist_sync_ack("mut_rust_ack_1", "", "2024-01-01T00:00:01Z").is_err());
    assert!(db
        .persist_sync_ack("mut_rust_ack_1", "not json", "2024-01-01T00:00:01Z")
        .is_err());
    assert!(db.persist_sync_ack("mut_rust_ack_1", "{\"ok\":true}", "").is_err());
    assert!(db
        .persist_sync_ack("missing_mutation", "{\"ok\":true}", "2024-01-01T00:00:01Z")
        .is_err());
    // Still pending after every rejected ack attempt.
    assert_eq!(db.list_pending_sync().unwrap().len(), 1);

    db.persist_sync_ack(
        "mut_rust_ack_1",
        "{\"receipt_id\":\"syncr_1\"}",
        "2024-01-01T00:00:02Z",
    )
    .unwrap();
    assert_eq!(db.list_pending_sync().unwrap().len(), 0);

    let counts = db.get_sync_counts().unwrap();
    assert_eq!(counts.acknowledged, 1);
    assert_eq!(counts.ack_persisted, 1);
    assert_eq!(counts.acknowledged_without_receipt, 0);
}

#[test]
fn update_mutation_state_rejects_unknown_and_terminal_transitions() {
    let dir = tempdir().unwrap();
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();
    db.enqueue_sync_mutation(&item("mut_rust_state_1", 1)).unwrap();

    // A command may never set `acknowledged` directly, nor invent a status.
    assert!(db
        .update_mutation_state("mut_rust_state_1", "acknowledged", None, "t")
        .is_err());
    assert!(db
        .update_mutation_state("mut_rust_state_1", "totally_synced", None, "t")
        .is_err());
    assert!(db
        .update_mutation_state("mut_rust_state_1", "'; DROP TABLE sync_outbox;--", None, "t")
        .is_err());

    db.update_mutation_state("mut_rust_state_1", "syncing", None, "2024-01-01T00:01:00Z")
        .unwrap();
    db.update_mutation_state(
        "mut_rust_state_1",
        "conflict",
        Some("DRAFT_CONFLICT"),
        "2024-01-01T00:02:00Z",
    )
    .unwrap();

    let row = db.get_sync_mutation("mut_rust_state_1").unwrap().unwrap();
    assert_eq!(row.sync_status, "conflict");
    assert_eq!(row.last_error.as_deref(), Some("DRAFT_CONFLICT"));
    assert_eq!(row.attempt_count, 1);

    db.persist_sync_ack("mut_rust_state_1", "{\"ok\":1}", "2024-01-01T00:03:00Z")
        .unwrap();
    // Acknowledged is terminal.
    assert!(db
        .update_mutation_state("mut_rust_state_1", "pending", None, "t")
        .is_err());
}

#[test]
fn queue_and_lease_survive_restart() {
    let dir = tempdir().unwrap();
    {
        let db = EncryptedDb::open(dir.path(), KEY).unwrap();
        db.cache_lease(&lease("sec_alpha_dc_w01", "2099-01-01T00:00:00Z"), "2024-01-01T00:00:00Z")
            .unwrap();
        db.enqueue_sync_mutation(&item("mut_rust_restart_1", 1)).unwrap();
        db.enqueue_sync_mutation(&item("mut_rust_restart_2", 2)).unwrap();
        db.update_mutation_state("mut_rust_restart_2", "syncing", None, "2024-01-01T00:01:00Z")
            .unwrap();
    }

    // Reopening decrypts the envelope written by the previous process.
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();
    let pending = db.list_pending_sync().unwrap();
    assert_eq!(pending.len(), 2);
    assert_eq!(pending[0].client_mutation_id, "mut_rust_restart_1");
    assert_eq!(pending[0].payload_json, "{\"percent_complete\":40}");

    let cached = db.get_section_lease("sec_alpha_dc_w01").unwrap().unwrap();
    assert_eq!(cached.lease_id, "lease_sec_alpha_dc_w01");
    assert!(cached.allows("quiz_attempt"));
    assert!(!cached.allows("attachment_queue"));

    let state = db
        .offline_state(Some("sec_alpha_dc_w01"), ts("2025-01-01T00:00:00Z"))
        .unwrap();
    assert!(state.lease_usable);
    assert_eq!(state.outstanding, 2);
    assert!(!state.all_work_acknowledged);
}

#[test]
fn revoked_and_expired_leases_are_not_usable() {
    let dir = tempdir().unwrap();
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();
    db.cache_lease(&lease("sec_a", "2099-01-01T00:00:00Z"), "2024-01-01T00:00:00Z")
        .unwrap();
    db.cache_lease(&lease("sec_b", "2099-01-01T00:00:00Z"), "2024-01-01T00:00:00Z")
        .unwrap();

    db.mark_lease_revoked("lease_sec_a", "instructor_revoked").unwrap();
    let a = db.get_section_lease("sec_a").unwrap().unwrap();
    assert!(a.revoked);
    assert!(!a.is_usable_at(ts("2025-01-01T00:00:00Z")));
    assert_eq!(a.revoke_reason.as_deref(), Some("instructor_revoked"));

    db.mark_lease_expired("lease_sec_b", "2024-06-01T00:00:00Z").unwrap();
    let b = db.get_section_lease("sec_b").unwrap().unwrap();
    assert!(!b.is_usable_at(ts("2025-01-01T00:00:00Z")));

    // An unparseable expiry is treated as expired, never as valid.
    let mut broken = lease("sec_c", "not-a-timestamp");
    broken.lease_id = "lease_broken".into();
    assert!(!broken.is_usable_at(ts("2025-01-01T00:00:00Z")));

    assert!(db.mark_lease_revoked("lease_missing", "x").is_err());
    assert_eq!(db.list_leases().unwrap().len(), 2);
}

#[test]
fn counts_and_status_listing_drive_the_banner() {
    let dir = tempdir().unwrap();
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();
    for (i, id) in ["mut_counts_1", "mut_counts_2", "mut_counts_3", "mut_counts_4"].iter().enumerate() {
        db.enqueue_sync_mutation(&item(id, i as i64 + 1)).unwrap();
    }
    db.update_mutation_state("mut_counts_2", "conflict", Some("CONFLICT"), "t").unwrap();
    db.update_mutation_state("mut_counts_3", "rejected", Some("ENROLLMENT_REVOKED"), "t")
        .unwrap();
    db.persist_sync_ack("mut_counts_4", "{\"result\":\"ok\"}", "t").unwrap();

    let counts = db.get_sync_counts().unwrap();
    assert_eq!(counts.pending, 1);
    assert_eq!(counts.conflict, 1);
    assert_eq!(counts.rejected, 1);
    assert_eq!(counts.acknowledged, 1);
    assert_eq!(counts.outstanding(), 1);
    assert_eq!(counts.needs_attention(), 2);

    assert_eq!(db.list_sync_by_status("conflict").unwrap().len(), 1);
    assert_eq!(db.list_sync_by_status("rejected").unwrap()[0].client_mutation_id, "mut_counts_3");
    assert!(db.list_sync_by_status("bogus").unwrap_err().to_string().contains("DB"));

    let state = db.offline_state(None, ts("2025-01-01T00:00:00Z")).unwrap();
    assert_eq!(state.outstanding, 1);
    assert_eq!(state.needs_attention, 2);
    assert!(!state.all_work_acknowledged);

    // Drain the queue: only then may the UI claim everything is in.
    db.persist_sync_ack("mut_counts_1", "{\"result\":\"ok\"}", "t").unwrap();
    db.update_mutation_state("mut_counts_2", "pending", None, "t").unwrap();
    db.persist_sync_ack("mut_counts_2", "{\"result\":\"ok\"}", "t").unwrap();
    db.update_mutation_state("mut_counts_3", "pending", None, "t").unwrap();
    db.persist_sync_ack("mut_counts_3", "{\"result\":\"ok\"}", "t").unwrap();
    let done = db.offline_state(None, ts("2025-01-01T00:00:00Z")).unwrap();
    assert!(done.all_work_acknowledged);
}

#[test]
fn enqueue_validates_input() {
    let dir = tempdir().unwrap();
    let db = EncryptedDb::open(dir.path(), KEY).unwrap();

    let mut short = item("tiny", 1);
    short.client_mutation_id = "short".into();
    assert!(db.enqueue_sync_mutation(&short).is_err());

    let mut bad_status = item("mut_bad_status_1", 1);
    bad_status.sync_status = "acknowledged".into();
    assert!(db.enqueue_sync_mutation(&bad_status).is_err());

    assert_eq!(db.next_local_sequence().unwrap(), 1);
    db.enqueue_sync_mutation(&item("mut_seq_ok_1", 1)).unwrap();
    assert_eq!(db.next_local_sequence().unwrap(), 2);
}
