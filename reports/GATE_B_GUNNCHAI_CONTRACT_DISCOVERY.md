# Gate B — gunnchAI contract discovery

Discovery date: 2026-09-06  
Platform branch: `cursor/waike-learning-gate-b-ai-18-tracks`  
Claim scope: **contract discovery + hub adapter** (not pedagogical effectiveness).

## Canonical repository

| Field | Value |
| --- | --- |
| Repo | https://github.com/gunnchOS3k/gunnchAI3k |
| Accepted SHA (main at discovery) | `4b4f411710e8cdb8102a7e11502f8497f68156b1` |
| Package name | `gunnchai3k` |
| Hub adapter | `services/hub/app/modules/gunnchai_adapter.py` |

## Modes (`src/waike-mastery/modes.ts`)

| Mode | mayReadInstructorKeys | mayDiscloseFinalAnswersToLearner | hitlGradingRequired | mayPublishGradesWithoutHuman |
| --- | --- | --- | --- | --- |
| `MASTERY_BENCHMARK` | false | false | false | false |
| `LEARNER_TUTOR` | false | false | false | false |
| `EDUCATOR_COPILOT` | true | false | true | false |

Ported to Python as `MODE_PERMISSIONS` + `assert_mode_permission`.

## Course discovery (`src/waike-mastery/contract.ts`)

- `resolveWaikeRoot` — env `WAIKE_REPO_ROOT` / `WAIKE_ROOT`, then sibling `waike-research-ops`
- `discoverCoursesFromContract` — reads `curriculum/digital_rc/*/course.json` (no hardcoded course names)

Hub endpoint: `GET /api/v1/ai/courses`

## Academic integrity (`src/tutor/academicIntegrityPolicy.ts`)

Cheat patterns refuse answer-key / active-exam solution requests. Practice quiz / mock exam / study guide remain allowed. Ported as `check_academic_integrity` + expanded isolation screens.

## Provider abstraction

| Provider | Role | Notes |
| --- | --- | --- |
| `FakeGunnchAIProvider` | **CI default** | Deterministic, no network, no keys |
| `LocalGunnchAIProvider` | Optional | Shells `npx tsx …/product_service/cli.ts assist` **only if** `GUNNCHAI_ROOT` set and CLI present; otherwise reports unavailable honestly |
| `CloudProviderStub` | Fail-closed | Mirrors gunnchAI cloud stub — `CLOUD_NOT_IMPLEMENTED` / consent required |

Env:

- `GUNNCHAI_PROVIDER=fake` (default / CI)
- `GUNNCHAI_ROOT` — optional checkout path
- No production API keys in CI or committed config

## Product-service CLI (local loopback)

```bash
npx tsx src/system-layer/product_service/cli.ts assist --capability tutoring --query "..."
```

Binds to 127.0.0.1 when served. Hub never invents a local GGUF/llama if absent.

## Privacy (`src/system-layer/privacy_policy.ts`)

- Default `processing_mode=local-only`
- Cloud fails closed without explicit `cloud_consent`
- Disclosure banner returned on every assist response

## Auth / instructor separation

- Learner assist → `LEARNER_TUTOR`; instructor context stripped
- Instructor assist → `EDUCATOR_COPILOT`; suggestions only; HITL required
- `POST /api/v1/ai/instructor/apply-grade` always returns `AI_SILENT_GRADE_FORBIDDEN`
- Server-authoritative AI policy (`AI_ALLOWED` \| `AI_HINTS_ONLY` \| `AI_DISABLED` \| `AI_INSTRUCTOR_DEFINED`); learners cannot set policy

## Offline

When no provider is available, hub returns `AI_PROVIDER_UNAVAILABLE` (503). No fabricated offline model claim.

## Tests

See `tests/gate_b/`:

- `test_gunnchai_contract.py`
- `test_ai_policy.py`
- `test_ai_context_isolation.py`
- `test_ai_prompt_injection.py`
- `test_ai_grade_safety.py`
- `test_adversarial_ai_sabotage.py` (§32)

```bash
WAIKE_ROOT=../waike-research-ops PYTHONPATH=services/hub .venv/bin/pytest -q tests/gate_b
```
