## Summary
- Gate A offline-first sync: leases, mutation ledger, durable receipts, conflict policy, attachment security, Device A/B E2E
- Complete activity engine: quizzes, labs (no fabricated hardware), discussions, groups, accommodations, grading efficiency
- Preserves PR1–PR3 guarantees (auth defaults, no default test seed, bootstrap-admin, site-scoped login, multi-role authz, receipts, rubric integrity)
- CI: `.github/workflows/gate-a.yml` with mandatory jobs; `make verify-gate-a`

## Test plan
- [ ] Remote Gate A required jobs green including verify-gate-a
- [ ] Local `make verify-gate-a`
- [ ] Owner review (do not auto-merge)

## Claim boundary
Earned only after green remote CI: `OFFLINE_AND_ACTIVITY_ENGINE_DIGITALLY_COMPLETE`.
Does not claim human/field/a11y/security certification or Gate B.
