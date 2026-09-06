# Gate B: gunnchAI and all 18 WAIKE tracks

## Summary
- Integrates canonical gunnchAI3k contracts (`4b4f411710e8cdb8102a7e11502f8497f68156b1`) via hub adapter + FakeGunnchAIProvider for CI.
- Server-authoritative AI policies (`AI_ALLOWED` / `AI_HINTS_ONLY` / `AI_DISABLED` / `AI_INSTRUCTOR_DEFINED`) with m005 migration; learner cannot alter policy; answer-key isolation + grade-safety enforced.
- Registry-driven course compiler produces signed learner + encrypted instructor packs for all 18 canonical WAIKE tracks (SEVEN_GC thin but honest).

## Claims (earned only after green remote Gate B CI)
- `GUNNCHAI_PLATFORM_INTEGRATION_DIGITALLY_COMPLETE`
- `ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE`
- `18_TRACK_PLATFORM_DELIVERY_DIGITALLY_COMPLETE`

## Does not claim
Human/field validation, accessibility/security certification, local GGUF/llama availability, pedagogical effectiveness, or Gate C.

## Test plan
- [ ] Remote `gate-b.yml` all mandatory jobs SUCCESS including `verify-gate-b`
- [ ] `make compile-18` + 18-track matrix PASS
- [ ] AI isolation / prompt-injection / grade-safety suites PASS
- [ ] install / learner / instructor / offline 18 suites PASS
