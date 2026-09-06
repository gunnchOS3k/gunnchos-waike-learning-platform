# Gate B — AI policy matrix

Server-authoritative policies stored via migration `m005` (`ai_policies`).
Learners cannot set policy. Effective resolution: **activity > assessment > section > default AI_ALLOWED**.

## Policies

| Policy | Learner capabilities | Instructor suggestions | Notes |
| --- | --- | --- | --- |
| `AI_ALLOWED` | explain, hint, misconception, remediation, citation, navigate, lab_troubleshoot, reflect | All instructor suggestion caps | Default when unset |
| `AI_HINTS_ONLY` | hint, navigate, reflect | All instructor suggestion caps | Explain/remediation blocked for learners |
| `AI_DISABLED` | none | none | Full refuse (`AI_DISABLED`) |
| `AI_INSTRUCTOR_DEFINED` | subset from `instructor_defined.allowed_capabilities` | subset or default instructor set | Requires non-empty capability list |

## Scope attachment

| Scope | Keys | Unique |
| --- | --- | --- |
| `section` | `section_id` | one row per section |
| `assessment` | `section_id` + `assessment_id` | per assessment |
| `activity` | `section_id` + `activity_id` | per activity (quiz/lab/…) |

## API

| Method | Path | Actor |
| --- | --- | --- |
| GET | `/api/v1/ai/policy?section_id=…` | enrolled / staff |
| POST | `/api/v1/ai/policy` | instructor-side only |
| POST | `/api/v1/ai/learner/assist` | learner |
| POST | `/api/v1/ai/instructor/assist` | instructor-side |

## Enforcement

| Check | Result code |
| --- | --- |
| Learner POST policy | `AI_POLICY_LEARNER_CANNOT_SET` / `INSTRUCTOR_ROLE_REQUIRED` |
| Capability not allowed | `AI_CAPABILITY_FORBIDDEN` |
| Policy disabled | `AI_DISABLED` |

## Evidence

- Module: `services/hub/app/modules/ai_policy.py`
- Tests: `tests/gate_b/test_ai_policy.py`
- JSON twin: `reports/GATE_B_AI_POLICY_MATRIX.json`
