# Gate B — AI security matrix

Isolation and sabotage coverage for Gate B §32. Adapter enforces gunnchAI modes from SHA `4b4f411710e8cdb8102a7e11502f8497f68156b1`.

## Threat → control → test

| # | Threat | Control | Refusal / status | Test |
| --- | --- | --- | --- | --- |
| 1 | Answer-key request | Academic integrity + cheat patterns | `AI_INTEGRITY_REFUSED` | `test_ai_context_isolation`, `test_adversarial_ai_sabotage` |
| 2 | Prompt injection in query | Injection regex screen | `AI_PROMPT_INJECTION` | `test_ai_prompt_injection` |
| 3 | Injection in uploaded/submitted content | Screen `course_materials` bodies | `AI_PROMPT_INJECTION` | `test_ai_prompt_injection`, §32 |
| 4 | Cross-learner data request | Cross-learner patterns | `AI_CROSS_LEARNER_FORBIDDEN` | isolation + §32 |
| 5 | System-prompt exfil | System exfil patterns | `AI_SYSTEM_PROMPT_EXFIL` | isolation + §32 |
| 6 | Instructor-context leak to learner | Instructor exfil patterns; strip keys from LEARNER_TUTOR | `AI_INSTRUCTOR_CONTEXT_LEAK` | isolation + §32 |
| 7 | Provider errors | Propagate `ServiceError` | `AI_PROVIDER_ERROR` (502) | §32 |
| 8 | Offline / missing runtime | Honest unavailable | `AI_PROVIDER_UNAVAILABLE` (503) | §32 + LocalGunnchAIProvider status |
| 9 | Silent grade change | AI apply-grade route refused always | `AI_SILENT_GRADE_FORBIDDEN` | `test_ai_grade_safety`, §32 |
| 10 | Cloud without consent | Privacy fail-closed | `cloudPermitted=false` / `AI_CLOUD_FORBIDDEN` | `test_gunnchai_contract` |
| 11 | Production keys in CI | Fake provider default | N/A (no keys) | contract discovery |
| 12 | Learner calling instructor assist | Role gate | 403 | isolation |

## Mode permissions (enforced in Python)

| Mode | Keys | Disclose finals | Publish grades w/o human |
| --- | --- | --- | --- |
| LEARNER_TUTOR | no | no | no |
| EDUCATOR_COPILOT | yes (HITL) | no | no |
| MASTERY_BENCHMARK | no | no | no |

## Provider posture

- CI: `FakeGunnchAIProvider` only
- Local CLI: optional via `GUNNCHAI_ROOT` — never fabricates GGUF/llama
- Cloud stub: fails closed

## Evidence

- Adapter: `services/hub/app/modules/gunnchai_adapter.py`
- Assist: `services/hub/app/modules/ai_assist.py`
- Tests: `tests/gate_b/test_adversarial_ai_sabotage.py` (+ related)
- JSON twin: `reports/GATE_B_AI_SECURITY_MATRIX.json`
