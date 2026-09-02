//! OS keyring for the local DB key, with documented DEV fallback.

use crate::error::AppError;
use keyring::Entry;
use rand::RngCore;

const SERVICE: &str = "com.gunnchos.waike.learning";
const ACCOUNT: &str = "local-db-key-v1";
const DEV_ENV: &str = "WAIKE_DEV_DB_KEY";

/// Resolve a 32-byte AES key.
///
/// Order:
/// 1. `WAIKE_DEV_DB_KEY` (64 hex chars) — **development only**, never production.
/// 2. OS keyring entry; created and stored on first use when available.
pub fn resolve_db_key() -> Result<([u8; 32], KeySource), AppError> {
    if let Ok(hex_key) = std::env::var(DEV_ENV) {
        let bytes = decode_hex_key(&hex_key)?;
        return Ok((bytes, KeySource::DevFallback));
    }

    match Entry::new(SERVICE, ACCOUNT) {
        Ok(entry) => match entry.get_password() {
            Ok(secret) => {
                let bytes = decode_hex_key(&secret)?;
                Ok((bytes, KeySource::Keyring))
            }
            Err(_) => {
                let mut key = [0u8; 32];
                rand::thread_rng().fill_bytes(&mut key);
                let hex = hex::encode(key);
                entry
                    .set_password(&hex)
                    .map_err(|e| AppError::Key(format!("keyring set failed: {e}")))?;
                Ok((key, KeySource::Keyring))
            }
        },
        Err(e) => Err(AppError::Key(format!(
            "keyring unavailable ({e}); set {DEV_ENV} for development"
        ))),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum KeySource {
    Keyring,
    DevFallback,
}

pub fn decode_hex_key(hex_key: &str) -> Result<[u8; 32], AppError> {
    let trimmed = hex_key.trim();
    let bytes = hex::decode(trimmed).map_err(|e| AppError::Key(format!("invalid hex key: {e}")))?;
    if bytes.len() != 32 {
        return Err(AppError::Key(format!(
            "DB key must be 32 bytes (64 hex chars), got {}",
            bytes.len()
        )));
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&bytes);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_valid_hex() {
        let hex = "00".repeat(32);
        let key = decode_hex_key(&hex).unwrap();
        assert_eq!(key.len(), 32);
    }
}
