## Summary
- PR3 multi-user LMS alpha: Argon2id/scrypt password hashing, secure sessions, sites, role assignments, sections/enrollment, site-admin APIs, instructor console, criterion grading, and deterministic gradebook.
- PR2 assessment lifecycle preserved under real identity (forward migration m003; fixture auth only behind explicit test config).
- Authoritative CI: `.github/workflows/pr3.yml` (pr2.yml manual-only). Local `verify-pr3` PASS.

## Test plan
- [ ] Remote CI required jobs green (contracts, migration, auth-security, authorization, multi-user-e2e, gradebook, hub, frontend, rust, security, accessibility, native-linux, macos artifact, verify-pr3)
- [ ] Confirm production defaults: `production_auth_enabled=true`, fixture headers rejected
- [ ] Confirm macOS artifact name `waike-learning-os-pr3-macos-<short-head>`
- [ ] Owner review + merge (do not auto-merge)

## Claim boundary
Earned only after remote CI green: `MULTI_USER_LMS_ALPHA_DIGITALLY_COMPLETE` / `PR3_READY_FOR_OWNER_REVIEW`.
Does **not** claim human/field/a11y/security certification or Wave 4 offline sync.
