# WAIKE Learning OS Platform

Native learning client and modular school-hub platform for WAIKE course packages.

This repository is authoritative for the installed client, package contracts, course compiler, school-hub application, and pilot runtime concerns. Curriculum authorship and the canonical course taxonomy remain in [`waike-research-ops`](https://github.com/gunnchOS3k/waike-research-ops). Device packaging and launcher policy remain in [`gunnchos-device-os`](https://github.com/gunnchOS3k/gunnchos-device-os).

## PR 1 scope

- Versioned package contracts and compatibility policy
- Deterministic course compiler for one real module: `DIGITAL_CONFIDENCE`
- Ed25519-signed learner packs and AES-256-GCM instructor packs
- Tauri 2 + React client that verifies before trust and persists lesson position in encrypted SQLite
- FastAPI school-hub scaffold (`/healthz`, version, config) with no live learner auth/data

## Quick start

```bash
make bootstrap
make verify-pr1
```

See `DEVELOPMENT.md`, `docs/product/CLAIM_BOUNDARY.md`, and `docs/product/PR1_ACCEPTANCE_MATRIX.md`.

## Not claimed

PR 1 does not claim full LMS parity, all-course migration, student validation, accessibility certification, production security review, or field-pilot completion.
