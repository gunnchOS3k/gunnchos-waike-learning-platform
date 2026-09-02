//! Encrypted-at-rest SQLite via AES-256-GCM file envelope (ADR-0003).

use crate::error::AppError;
use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Nonce};
use rand::RngCore;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

const NONCE_LEN: usize = 12;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstalledPack {
    pub pack_id: String,
    pub module_id: String,
    pub track_id: String,
    pub title: String,
    pub content_root_sha256: String,
    pub source_commit: String,
    pub schema_version: String,
    pub verification_status: String,
    pub install_path: String,
    pub content_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LessonPosition {
    pub pack_id: String,
    pub lesson_id: String,
    pub path: String,
    pub scroll_offset: f64,
    pub updated_utc: String,
}

pub struct EncryptedDb {
    enc_path: PathBuf,
    plain_path: PathBuf,
    key: [u8; 32],
    conn: Connection,
}

impl EncryptedDb {
    pub fn open(data_dir: &Path, key: [u8; 32]) -> Result<Self, AppError> {
        fs::create_dir_all(data_dir)?;
        let enc_path = data_dir.join("state.db.enc");
        let plain_path = data_dir.join("state.sqlite.tmp");
        if enc_path.is_file() {
            let blob = fs::read(&enc_path)?;
            if blob.len() < NONCE_LEN + 16 {
                return Err(AppError::Db("corrupt encrypted db".into()));
            }
            let nonce = Nonce::from_slice(&blob[..NONCE_LEN]);
            let cipher = Aes256Gcm::new_from_slice(&key).map_err(|e| AppError::Key(e.to_string()))?;
            let plain = cipher
                .decrypt(nonce, &blob[NONCE_LEN..])
                .map_err(|_| AppError::Db("db decrypt failed".into()))?;
            fs::write(&plain_path, plain)?;
        } else if plain_path.exists() {
            // leave existing temp
        } else {
            let conn = Connection::open(&plain_path)?;
            Self::migrate(&conn)?;
            drop(conn);
        }
        let conn = Connection::open(&plain_path)?;
        // Prefer rollback journal so the on-disk sqlite file is complete after checkpoint.
        conn.execute_batch("PRAGMA journal_mode=DELETE;")?;
        Self::migrate(&conn)?;
        let db = Self {
            enc_path,
            plain_path,
            key,
            conn,
        };
        db.persist_envelope()?;
        Ok(db)
    }

    fn migrate(conn: &Connection) -> Result<(), AppError> {
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS installed_packs (
                pack_id TEXT PRIMARY KEY,
                module_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content_root_sha256 TEXT NOT NULL,
                source_commit TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                install_path TEXT NOT NULL,
                content_version TEXT NOT NULL
             );
             CREATE TABLE IF NOT EXISTS lesson_position (
                pack_id TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                path TEXT NOT NULL,
                scroll_offset REAL NOT NULL DEFAULT 0,
                updated_utc TEXT NOT NULL,
                PRIMARY KEY(pack_id, lesson_id)
             );",
        )?;
        Ok(())
    }

    pub fn persist_envelope(&self) -> Result<(), AppError> {
        // Flush WAL into the main sqlite file, then encrypt those bytes.
        let _ = self.conn.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);");
        let plain = fs::read(&self.plain_path)?;
        let cipher = Aes256Gcm::new_from_slice(&self.key).map_err(|e| AppError::Key(e.to_string()))?;
        let mut nonce_bytes = [0u8; NONCE_LEN];
        rand::thread_rng().fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);
        let ct = cipher
            .encrypt(nonce, plain.as_ref())
            .map_err(|e| AppError::Db(e.to_string()))?;
        let mut out = Vec::with_capacity(NONCE_LEN + ct.len());
        out.extend_from_slice(&nonce_bytes);
        out.extend_from_slice(&ct);
        fs::write(&self.enc_path, out)?;
        Ok(())
    }

    pub fn upsert_pack(&self, pack: &InstalledPack) -> Result<(), AppError> {
        self.conn.execute(
            "INSERT INTO installed_packs(
                pack_id, module_id, track_id, title, content_root_sha256, source_commit,
                schema_version, verification_status, install_path, content_version
             ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)
             ON CONFLICT(pack_id) DO UPDATE SET
                module_id=excluded.module_id,
                track_id=excluded.track_id,
                title=excluded.title,
                content_root_sha256=excluded.content_root_sha256,
                source_commit=excluded.source_commit,
                schema_version=excluded.schema_version,
                verification_status=excluded.verification_status,
                install_path=excluded.install_path,
                content_version=excluded.content_version",
            (
                &pack.pack_id,
                &pack.module_id,
                &pack.track_id,
                &pack.title,
                &pack.content_root_sha256,
                &pack.source_commit,
                &pack.schema_version,
                &pack.verification_status,
                &pack.install_path,
                &pack.content_version,
            ),
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    pub fn get_pack(&self, pack_id: &str) -> Result<Option<InstalledPack>, AppError> {
        let mut stmt = self.conn.prepare(
            "SELECT pack_id, module_id, track_id, title, content_root_sha256, source_commit,
                    schema_version, verification_status, install_path, content_version
             FROM installed_packs WHERE pack_id=?1",
        )?;
        let mut rows = stmt.query([pack_id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(InstalledPack {
                pack_id: row.get(0)?,
                module_id: row.get(1)?,
                track_id: row.get(2)?,
                title: row.get(3)?,
                content_root_sha256: row.get(4)?,
                source_commit: row.get(5)?,
                schema_version: row.get(6)?,
                verification_status: row.get(7)?,
                install_path: row.get(8)?,
                content_version: row.get(9)?,
            }))
        } else {
            Ok(None)
        }
    }

    pub fn list_packs(&self) -> Result<Vec<InstalledPack>, AppError> {
        let mut stmt = self.conn.prepare(
            "SELECT pack_id, module_id, track_id, title, content_root_sha256, source_commit,
                    schema_version, verification_status, install_path, content_version
             FROM installed_packs ORDER BY pack_id",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(InstalledPack {
                pack_id: row.get(0)?,
                module_id: row.get(1)?,
                track_id: row.get(2)?,
                title: row.get(3)?,
                content_root_sha256: row.get(4)?,
                source_commit: row.get(5)?,
                schema_version: row.get(6)?,
                verification_status: row.get(7)?,
                install_path: row.get(8)?,
                content_version: row.get(9)?,
            })
        })?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn save_position(&self, pos: &LessonPosition) -> Result<(), AppError> {
        self.conn.execute(
            "INSERT INTO lesson_position(pack_id, lesson_id, path, scroll_offset, updated_utc)
             VALUES (?1,?2,?3,?4,?5)
             ON CONFLICT(pack_id, lesson_id) DO UPDATE SET
               path=excluded.path,
               scroll_offset=excluded.scroll_offset,
               updated_utc=excluded.updated_utc",
            (
                &pos.pack_id,
                &pos.lesson_id,
                &pos.path,
                pos.scroll_offset,
                &pos.updated_utc,
            ),
        )?;
        self.persist_envelope()?;
        Ok(())
    }

    pub fn get_position(&self, pack_id: &str, lesson_id: &str) -> Result<Option<LessonPosition>, AppError> {
        let mut stmt = self.conn.prepare(
            "SELECT pack_id, lesson_id, path, scroll_offset, updated_utc
             FROM lesson_position WHERE pack_id=?1 AND lesson_id=?2",
        )?;
        let mut rows = stmt.query((pack_id, lesson_id))?;
        if let Some(row) = rows.next()? {
            Ok(Some(LessonPosition {
                pack_id: row.get(0)?,
                lesson_id: row.get(1)?,
                path: row.get(2)?,
                scroll_offset: row.get(3)?,
                updated_utc: row.get(4)?,
            }))
        } else {
            Ok(None)
        }
    }

    pub fn latest_position(&self, pack_id: &str) -> Result<Option<LessonPosition>, AppError> {
        let mut stmt = self.conn.prepare(
            "SELECT pack_id, lesson_id, path, scroll_offset, updated_utc
             FROM lesson_position WHERE pack_id=?1
             ORDER BY updated_utc DESC LIMIT 1",
        )?;
        let mut rows = stmt.query([pack_id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(LessonPosition {
                pack_id: row.get(0)?,
                lesson_id: row.get(1)?,
                path: row.get(2)?,
                scroll_offset: row.get(3)?,
                updated_utc: row.get(4)?,
            }))
        } else {
            Ok(None)
        }
    }
}

impl Drop for EncryptedDb {
    fn drop(&mut self) {
        let _ = self.persist_envelope();
        let _ = fs::remove_file(&self.plain_path);
        let _ = fs::remove_file(format!("{}-wal", self.plain_path.display()));
        let _ = fs::remove_file(format!("{}-shm", self.plain_path.display()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn envelope_roundtrip_restart() {
        let dir = tempdir().unwrap();
        let key = [7u8; 32];
        {
            let db = EncryptedDb::open(dir.path(), key).unwrap();
            db.upsert_pack(&InstalledPack {
                pack_id: "p1".into(),
                module_id: "DIGITAL_CONFIDENCE".into(),
                track_id: "DIGITAL_CONFIDENCE".into(),
                title: "DC".into(),
                content_root_sha256: "abc".into(),
                source_commit: "deadbeef".into(),
                schema_version: "1.0.0".into(),
                verification_status: "verified".into(),
                install_path: "/tmp".into(),
                content_version: "1.0.0".into(),
            })
            .unwrap();
            db.save_position(&LessonPosition {
                pack_id: "p1".into(),
                lesson_id: "L1".into(),
                path: "x.md".into(),
                scroll_offset: 12.5,
                updated_utc: "2024-01-01T00:00:00Z".into(),
            })
            .unwrap();
        }
        let db2 = EncryptedDb::open(dir.path(), key).unwrap();
        let pack = db2.get_pack("p1").unwrap().unwrap();
        assert_eq!(pack.module_id, "DIGITAL_CONFIDENCE");
        let pos = db2.get_position("p1", "L1").unwrap().unwrap();
        assert!((pos.scroll_offset - 12.5).abs() < f64::EPSILON);
    }
}
