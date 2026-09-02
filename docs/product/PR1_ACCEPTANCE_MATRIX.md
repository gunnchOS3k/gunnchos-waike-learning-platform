# PR 1 acceptance matrix

| Gate | Evidence | Result |
|------|----------|--------|
| Contracts JSON Schema 2020-12 (9 schemas) | `contracts/schemas/*`, pytest compatibility | Required |
| Fail-closed unknown module IDs | `tests/integration` | Required |
| DIGITAL_CONFIDENCE real import (no invented lessons) | `reports/DIGITAL_CONFIDENCE_IMPORT_REPORT.*` | Required |
| Learner/instructor split | security tests 06–08 | Required |
| Ed25519 learner sign + AES-GCM instructor | compiler + security suite | Required |
| Ten crypto separation negatives | `tests/security/test_crypto_separation.py` | Required |
| Compatibility typed rejection reasons | `tests/compatibility` | Required |
| Hub `/healthz` `/version` config; no auth/data | `services/hub/tests` | Required |
| Tauri client verify-before-trust + encrypted SQLite progress | `cargo test` | Required |
| Frontend trust/lesson/resume/error/a11y basics | `apps/client` vitest | Required |
| `make verify-pr1` aggregator honest PASS/BLOCKED | `reports/pr1_verification.json` | Required |
| Native GUI build | attempted; may be BLOCKED on CI Linux without webview | Recorded honestly |

Claim earned only when aggregator status is `AUTOMATED_PIPELINE_PASS`:

`digitally implemented and automatically tested for PR 1 scope`
