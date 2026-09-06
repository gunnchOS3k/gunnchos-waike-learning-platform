# Gate B Adversarial Review — Surgical Closure

Structured adversarial pass for Gate B AI isolation + 18-track package security.
**Do not claim zero blockers** until remote Gate B (§15 matrix) is green on the final head.
**Do not claim ALL_18** while `SEVEN_GC_SOURCE_BLOCKS_18_OF_18` holds.

## Closure findings (§14)

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| GB-C1 | merge-blocking | Fake AI production default | **Fixed (B1)** — `DEFAULT_RUNTIME_HAS_NO_FAKE_AI`; fake via injection / allow-flag only |
| GB-C2 | merge-blocking | No canonical gunnchAI checkout | **Fixed (B2)** — CI checkout + `GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT`; drift fails |
| GB-C3 | merge-blocking | Client-supplied grounding citations | **Fixed (B3)** — server-resolved learner pack materials; hashed citations |
| GB-C4 | merge-blocking | SEVEN_GC shell PASS for all-18 | **Honest (B5)** — matrix `BLOCKED`; ALL_18 claims withheld; no invented digital_rc |
| GB-C5 | merge-blocking | DC / Gate A activity stand-ins | **Fixed (B6)** — pack→hub import; `module_id == track_id` |
| GB-C6 | merge-blocking | PENDING_SUITE acceptance | **Fixed (B7)** |
| GB-C7 | merge-blocking | Required test skips | **Fixed (B8)** — `GATE_B_REQUIRED_TESTS_SKIPPED=0` |
| GB-C8 | merge-blocking | Red historical Gate A / PR3 workflows | **Fixed (B10)** — `workflow_dispatch`; Gate B `full-prior-regression` |
| GB-C9 | merge-blocking | Structural isolation / audit redaction / real-provider honesty | **Fixed (B4/B9 + authz/audit)** |

## Remaining honesty / process blockers

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| GB-R1 | claim | ALL_18 / 18_TRACK delivery claims | **Blocked by authentic source** — `SEVEN_GC_SOURCE_BLOCKS_18_OF_18` |
| GB-R2 | process | Remote expanded Gate B CI on final head | **Pending push / CI self-heal** |
| GB-R3 | non-blocking | Human live-provider adversarial review | Pending |
| GB-R4 | non-blocking | A11y / security certification | Not claimed |

## Provider posture

- Production default: Local if CLI present, else Unavailable → `AI_PROVIDER_UNAVAILABLE` 503
- Fake: constructor injection or `GUNNCHAI_PROVIDER=fake` + `WAIKE_ALLOW_FAKE_AI=1` only
- Contract vs real: `GUNNCHAI_CONTRACT_INTEGRATION_COMPLETE` ≠ `GUNNCHAI_REAL_PROVIDER_AVAILABLE`
- No fabricated GGUF/llama claim

## Grounding posture

- Learner `course_materials` removed from API body / client
- Citations only from enrolled section's installed learner-visible pack content
- `grounded=true` only with validated `content_hash` citations

## Test honesty

- Zero-count activities → `NOT_APPLICABLE` (not skip)
- SEVEN_GC shell → `BLOCKED` (not PASS)
- Matrix: 17 PASS + 1 BLOCKED
- Verifier rejects fake-default, contract drift, PENDING_SUITE, required skips, false ALL_18

## Evidence

- Adapter / assist: `services/hub/app/modules/gunnchai_adapter.py`, `ai_assist.py`
- Verifier: `scripts/verify_gate_b.py`, `scripts/verify_gunnchai_contract.py`
- Suites: `tests/gate_b/*`
- CI: `.github/workflows/gate-b.yml`
