# PR2 acceptance matrix — Assessment lifecycle

| Gate | Evidence | Result |
|------|----------|--------|
| Real WAIKE DIGITAL_CONFIDENCE assignment seed (`digital_confidence_w01`) | `AssessmentService.seed_digital_confidence_assignment`, week_01.yaml | Required |
| Versioned domain contracts (16 entities) | `contracts/schemas/assessment_lifecycle/*` | Required |
| Hub migrations for assessment persistence | `services/hub/app/migrations/m001_assessment_lifecycle.py` | Required |
| Learner draft autosave + restart preserve | E2E steps 2–3 | Required |
| Submit + immutable receipt + idempotency | E2E steps 4–5 | Required |
| Instructor queue + rubric grade + feedback | E2E steps 6–8 | Required |
| Gradebook entry | E2E step 8 | Required |
| Mastery gap + remediation | E2E steps 9–10 | Required |
| Resubmission + regrade + mastery update | E2E steps 11–13 | Required |
| Portfolio evidence | E2E step 14 | Required |
| Unauthorized access negatives (server-side) | E2E step 15 | Required |
| Learner/instructor UI without dead claimed buttons | `AssessmentWorkspace`, `InstructorQueue`, vitest | Required |
| Encrypted local learner storage retained (PR1) | Tauri progress DB unchanged | Required |
| Provenance gate preserved | PIN.json + CI align step | Required |
| `make verify-pr2` / `scripts/verify_pr2.py` honest PASS/BLOCKED | reports/PR2_VERIFICATION.* | Required |
| Remote PR2 workflow required jobs SUCCESS | `.github/workflows/pr2.yml` | Required |

Claim earned only when aggregator status is `AUTOMATED_PIPELINE_PASS` **and** remote CI green:

`ASSESSMENT_LIFECYCLE_DIGITALLY_COMPLETE`
