# Gate B Adversarial Review

Structured adversarial pass for Gate B AI isolation + 18-track package security.
Automated sabotage suite exists; **human review pending**.

## Scope reviewed

| Area | Evidence |
|------|----------|
| AI policy enforcement | `tests/gate_b/test_ai_policy.py`, `services/hub/app/modules/ai_policy.py` |
| Context isolation | `tests/gate_b/test_ai_context_isolation.py`, `ai_assist.py` |
| Prompt injection | `tests/gate_b/test_ai_prompt_injection.py` |
| Grade safety | `tests/gate_b/test_ai_grade_safety.py` (apply-grade hard-refused) |
| GunnchAI contract | `tests/gate_b/test_gunnchai_contract.py` + discovery report |
| Automated sabotage | `tests/gate_b/test_adversarial_ai_sabotage.py` (§32 suite) |
| Compiler / pack security | `tests/gate_b/test_package_security_18.py`, `test_compiler_18.py` |

## Findings (code-reading pass)

| ID | Severity | Area | Finding | Status |
|----|----------|------|---------|--------|
| GB-A1 | merge-blocking if unfixed | integrity | Learner AI must refuse answer-key / instructor-packet exfil | Covered by isolation + sabotage tests (automated) |
| GB-A2 | merge-blocking if unfixed | integrity | Prompt injection in uploaded materials must refuse or strip keys | Covered by `AI_PROMPT_INJECTION` / citation strip tests |
| GB-A3 | merge-blocking if unfixed | authz | Cross-learner and cross-section AI context must fail closed | Covered by context isolation suite |
| GB-A4 | merge-blocking if unfixed | grading | AI must never mutate grades (`apply-grade` refused) | Covered by grade-safety + instructor panel UX |
| GB-A5 | merge-blocking if unfixed | packages | Learner packs must verify Ed25519; instructor AES decrypt path-contained | Covered by package-security-18 |
| GB-A6 | honesty | content | `SEVEN_GC_APPRENTICESHIP` has no digital_rc weeks (0 lessons/quizzes/labs) | Honest thin inventory; E2E skips zero-count activity types |
| GB-A7 | non-blocking | a11y | AI panel a11y is smoke-only, not certification | `a11y.gate-b.test.tsx` |
| GB-A8 | non-blocking | process | Human adversarial review of live gunnchAI provider behavior not completed | **Pending** — automated Fake provider + contract discovery only |

## Accepted trust boundaries

- Fake / stub GunnchAI provider is authoritative in CI; live provider contract is discovery-documented, not field-certified.
- Compiler security proves signature + decrypt + path containment on fixtures keys — not production key ceremony.
- Track E2E uses hub activity seeds for quiz/lab when inventory counts > 0; it does not invent missing curriculum files for thin tracks.
- Offline column in the 18-track matrix reflects `offline_pack` presence in the learner pack, not a claim of full offline curriculum mirroring for every track.

## Merge-blocking open (human)

Human review of production GunnchAI wiring and red-team of live prompts remains **pending**. Automated sabotage suite is the current gate.

## Test honesty

- Zero-count activity types are skipped, not fabricated.
- Matrix `instructor_visible=EMPTY` for thin instructor packs is preserved.
- Remote Gate B claim withheld until required `gate-b.yml` jobs (including `verify-gate-b`) are green on the final head.
