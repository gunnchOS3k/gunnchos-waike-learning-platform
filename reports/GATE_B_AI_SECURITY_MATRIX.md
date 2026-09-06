# Gate B — AI security matrix

Isolation and sabotage coverage for Gate B. Adapter enforces gunnchAI modes from SHA `4b4f411710e8cdb8102a7e11502f8497f68156b1`.

## Threat → control → test

| # | Threat | Control | Refusal / status | Test |
| --- | --- | --- | --- | --- |
| 1 | Answer-key request | Academic integrity + structural strip | `AI_INTEGRITY_REFUSED` | isolation + sabotage |
| 2 | Prompt injection in query | Injection regex (defense-in-depth) | `AI_PROMPT_INJECTION` | prompt-injection |
| 3 | Forged / client materials as citations | Server-resolved grounding only | ignored / not grounded | grounding-integrity + sabotage |
| 4 | Cross-learner data | Structural + pattern | `AI_CROSS_LEARNER_FORBIDDEN` | isolation |
| 5 | System-prompt exfil | Patterns | `AI_SYSTEM_PROMPT_EXFIL` | isolation |
| 6 | Instructor-context leak | Structural zero keys to learner provider | `AI_INSTRUCTOR_CONTEXT_LEAK` | EchoTestProvider + isolation |
| 7 | Provider errors | Propagate `ServiceError` | `AI_PROVIDER_ERROR` (502) | sabotage |
| 8 | Missing runtime | Honest unavailable | `AI_PROVIDER_UNAVAILABLE` (503) | sabotage + contract |
| 9 | Silent grade change | Apply-grade refused | `AI_SILENT_GRADE_FORBIDDEN` | grade-safety |
| 10 | Fake AI in production | Default Unavailable/Local; fake needs allow-flag | `AI_FAKE_PROVIDER_FORBIDDEN` / unavailable | production-ai-no-fake |
| 11 | Audit privacy | Hash-only audit; no raw query/keys/bodies | redacted | audit-redaction |

## Provider posture

- Label: `DEFAULT_RUNTIME_HAS_NO_FAKE_AI`
- Fake only via explicit test injection or `GUNNCHAI_PROVIDER=fake` + `WAIKE_ALLOW_FAKE_AI=1`
- Local CLI optional via `GUNNCHAI_ROOT` — never fabricates GGUF/llama
- Cloud stub fails closed

## Evidence

- Adapter: `services/hub/app/modules/gunnchai_adapter.py`
- Assist: `services/hub/app/modules/ai_assist.py`
- Tests: `tests/gate_b/test_adversarial_ai_sabotage.py`, `test_ai_grounding_integrity.py`, `test_ai_audit_redaction.py`, `test_production_ai_no_fake.py`
