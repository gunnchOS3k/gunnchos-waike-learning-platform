# Gate D PR body

## Summary
- Clean-room full-system acceptance gate on accepted main after Gate C merge (`58daf1a…`).
- Adds guardian least-privilege role + linked-learner overview (no answer keys / grading / admin).
- `make verify-gate-d` + `.github/workflows/gate-d.yml` exercise all 16 acceptance scopes with fail-closed CI.
- Final claim-integrity closure: required accommodations + mastery/remediation, semantic journey verification, measured clean-room, adversarial soft-pass sabotage.

## Pins
- Device OS: `4f02a48780d300a5d3a7758937b20e3bf9364d0d`
- WAIKE: `fbf7685bc5686201ccaa0128ee83346d59b3d584`
- gunnchAI: `4b4f411710e8cdb8102a7e11502f8497f68156b1`

## Claims (earned only when remote Gate D CI green on exact head)
- `AUTOMATED_FULL_PLATFORM_PASS`
- `ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE`
- `LEARNER_AND_INSTRUCTOR_WORKFLOWS_DIGITALLY_COMPLETE`
- `READY_FOR_STAFF_ALPHA_AND_HUMAN_VALIDATION`

## FULL_COMPLETION_STATE distinction
- **Committed** `reports/FULL_COMPLETION_STATE.json` is a **PENDING_FINAL_EXACT_HEAD_CI** baseline (`claims_earned: []`, `owner_action: GATE_D_NOT_READY`). It is not earned proof.
- **This-run CI artifact** `gate-d-reports-<HEAD>/FULL_COMPLETION_STATE.json` is written by `verify-gate-d` after semantic + native + Device OS checks. That artifact is the only earned-claim source of truth for the exact head SHA.
- Do not post-green commit artifact evidence in a way that invalidates the head SHA binding.

## Out of scope (external ledger)
Physical Device Quartet, production notarization, WCAG/FERPA/OneRoster/QTI/LTI certification, field pilot.

## Owner action when earned
`MERGE_GATE_D_FINAL_ACCEPTANCE`
