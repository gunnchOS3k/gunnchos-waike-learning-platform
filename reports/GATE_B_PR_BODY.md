# Gate B: gunnchAI and 18 WAIKE tracks (surgical closure)

## Summary
- Canonical gunnchAI3k pin `4b4f411710e8cdb8102a7e11502f8497f68156b1` checked out in CI; adapter verified against real source files (`GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT`); drift fails `GUNNCHAI_CONTRACT_DRIFT`.
- **No fake AI in production defaults** (`DEFAULT_RUNTIME_HAS_NO_FAKE_AI`). Unset provider → unavailable 503. Fake only via explicit test injection or `GUNNCHAI_PROVIDER=fake` + `WAIKE_ALLOW_FAKE_AI=1`.
- Server-resolved learner grounding from enrollment + installed pack learner-visible content; validated citations with content hash; `grounded=true` only when validated.
- Structural learner isolation (zero instructor/answer-key/peer paths to provider); audit redaction (hashes only).
- 18-track compiler matrix: **17 PASS + SEVEN_GC `BLOCKED`** (`SEVEN_GC_SOURCE_BLOCKS_18_OF_18`). No invented SEVEN_GC digital_rc. No WAIKE cross-repo PR (authentic sources forbid invention).
- Per-track E2E imports packaged activities (`module_id == track_id`); no DC/Gate A stand-ins; zero-count → `NOT_APPLICABLE`.
- Acceptance from executed evidence only (no `PENDING_SUITE`); `GATE_B_REQUIRED_TESTS_SKIPPED=0`.
- Historical Gate A / PR3 workflows → `workflow_dispatch`; Gate B `full-prior-regression` required by `verify-gate-b`.

## Claims
- Earned when remote Gate B CI is green: `GUNNCHAI_PLATFORM_INTEGRATION_DIGITALLY_COMPLETE`
- **Not earned** (authentic source): `ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE`, `18_TRACK_PLATFORM_DELIVERY_DIGITALLY_COMPLETE`
- Separate honesty: `GUNNCHAI_REAL_PROVIDER_AVAILABLE` only when local product-service CLI is present — not claimed as inference unless assist ran.

## Does not claim
Human/field validation, a11y/security certification, local GGUF/llama inference, pedagogical effectiveness, Gate C, invented SEVEN_GC digital course content, production signing/notarization.

## Test plan
- [ ] Remote `gate-b.yml` all mandatory §15 jobs SUCCESS including `verify-gate-b` and `full-prior-regression`
- [ ] No active red Gate A / PR3 workflows on PR pushes
- [ ] Contract snapshot PASS against pinned gunnchAI
- [ ] production-ai-no-fake / grounding / audit-redaction / adversarial suites PASS
- [ ] 17 digital tracks PASS; SEVEN_GC BLOCKED; acceptance has zero PENDING_SUITE / zero required skips
