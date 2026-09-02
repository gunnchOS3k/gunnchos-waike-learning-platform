# Contributing

## Workflow

1. Branch from `main` (or the active PR 1 branch until it merges).
2. Keep curriculum authorship in `waike-research-ops` — do not re-author lessons here.
3. Run `make bootstrap` then `make verify-pr1` before opening or updating a PR.
4. Open draft PRs for review; do not merge your own foundation gate without owner approval.

## Conventions

- Python 3.11+ with `uv` preferred.
- TypeScript + React for the client UI; Rust for pack verification and local storage.
- Prefer established crypto libraries only (`cryptography`, `PyNaCl`, Rust `ed25519-dalek` / `aes-gcm`).
- Record architecture decisions in `docs/adr/`.

## Secrets

Never commit production keys, learner PII, grades, or pilot data.
