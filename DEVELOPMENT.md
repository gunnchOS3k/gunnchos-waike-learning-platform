# Development

## Prerequisites

- Python 3.11+
- Node.js 20+ and npm or pnpm
- Rust stable (via rustup) for the Tauri client
- A sibling checkout of `waike-research-ops` (see `curriculum/registry/PIN.json`)

## Bootstrap

```bash
make bootstrap
```

This creates `.venv`, installs the course compiler and hub deps, and installs client npm packages.

## Common commands

```bash
make lint
make test
make build
make verify-pr1
```

## Compile DIGITAL_CONFIDENCE

```bash
export SOURCE_DATE_EPOCH=1700000000
.venv/bin/course-compiler compile DIGITAL_CONFIDENCE --out pack_out
```

## Hub (PR3)

```bash
# Production-shaped runtime: never auto-seeds Alpha/Beta test accounts.
PYTHONPATH=services/hub .venv/bin/uvicorn app.main:app --app-dir services/hub --reload

# One-time first admin (password via getpass or WAIKE_BOOTSTRAP_ADMIN_PASSWORD — never argv):
PYTHONPATH=services/hub .venv/bin/python -m app.cli bootstrap-admin \
  --site-id site-prod --site-name "Prod Site" \
  --username root-admin --display-name "Root Admin"

# Synthetic fixtures only for tests (seed=True) or explicit:
#   WAIKE_SEED_TEST_FIXTURES=true WAIKE_ENV=development
```

Login requires `site_id` (usernames are site-scoped).

## Encrypted local storage (dev fallback)

The Tauri core encrypts the SQLite database file with AES-256-GCM.
In development, set `WAIKE_DEV_DB_KEY` to a 64-hex-character key if OS keyring is unavailable.
This fallback is documented and must not be treated as production key management.
See `docs/adr/ADR-0003-encrypted-local-storage.md`.

## WAIKE pin

Update `curriculum/registry/PIN.json` when the taxonomy export commit changes.
