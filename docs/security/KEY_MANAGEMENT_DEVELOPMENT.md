# Key management (development)

## Test-only package keys

Located at `contracts/fixtures/keys/`:

- `TEST_ONLY_ed25519_private.key` / `TEST_ONLY_ed25519_public.key`
- `TEST_ONLY_instructor_aes256.key`
- `TEST_ONLY_key_manifest.json`

These keys are for automated tests and local demos only. Never use them in production.

## Local database key

- Preferred: OS keyring entry  
  - service: `com.gunnchos.waike.learning`  
  - account: `local-db-key-v1`
- Development fallback: environment variable `WAIKE_DEV_DB_KEY` (exactly 64 hex characters → 32-byte AES key).

The Makefile and CI set `WAIKE_DEV_DB_KEY` for reproducible encrypted-SQLite tests. This fallback is **not** production key management.

Never commit real device or production keys. Rotate any key that leaks outside fixtures.
