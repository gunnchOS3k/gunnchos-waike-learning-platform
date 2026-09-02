# ADR-0003: Encrypted local storage

## Status

Accepted (PR 1)

## Context

Lesson position and install metadata must persist across restarts without using browser `localStorage` as the system of record. Prefer SQLCipher or an equivalently established SQLite encryption path. SQLCipher linking (OpenSSL/SQLCipher system libs) is brittle on some macOS toolchains and slows CI bootstrap.

## Decision

**Chosen approach: AES-256-GCM envelope over a normal SQLite file** (rusqlite with the `bundled` feature).

- On-disk artifact: `state.db.enc` = 12-byte nonce || AES-256-GCM ciphertext of the SQLite database bytes.
- Runtime: decrypt to a temporary SQLite file, run migrations/queries with rusqlite, re-encrypt on each transactional close.
- **Not SQLCipher** for PR 1, due to macOS linking pain. Revisit SQLCipher if Device OS packaging standardizes a supported build path.
- Database key: OS keyring service `com.gunnchos.waike.learning` / account `local-db-key-v1`.
- Development fallback: `WAIKE_DEV_DB_KEY` (64 hex characters). Explicitly non-production. See `docs/security/KEY_MANAGEMENT_DEVELOPMENT.md`.

## Consequences

Encrypted-at-rest local state with workable CI/dev ergonomics. Production deployments must use OS keyring and must not rely on `WAIKE_DEV_DB_KEY`. Browser storage remains UI-only and is not authoritative.
