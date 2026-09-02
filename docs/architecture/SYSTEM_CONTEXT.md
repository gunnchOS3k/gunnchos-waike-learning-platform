# System context

WAIKE Learning OS is a local-first, installed learning platform for gunnchOS.

## Actors

- **Learner** — installs signed learner packs, reads lessons, persists progress locally.
- **Instructor** (future) — unlocks encrypted instructor packs with authorized keys.
- **School hub** — future enrollment, sync, gradebook; PR 1 exposes health/version only.
- **Curriculum authors** — work in `waike-research-ops`, not this repository.

## Runtime containers

| Component | Tech | PR 1 role |
|-----------|------|-----------|
| Client | Tauri 2 + React + Rust core | Verify/install packs, lesson reader, encrypted local state |
| Course compiler | Python | Import WAIKE sources → signed/encrypted packs |
| School hub | FastAPI | Scaffold only (`/healthz`, `/version`, config) |
| Contracts | JSON Schema | Package and compatibility validation |

## Trust boundary

Unsigned or failed verification packages must never become trusted UI content. Instructor material is a separate encrypted artifact.
