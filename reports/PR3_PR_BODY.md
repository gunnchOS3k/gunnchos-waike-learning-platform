## Summary
- PR3 multi-user LMS alpha: Argon2id/scrypt password hashing, secure sessions, sites, role assignments, sections/enrollment, site-admin APIs, instructor console, criterion grading, and deterministic gradebook.
- **Final identity/security closure:** default runtime never seeds Alpha/Beta test accounts or `WaikeTestPass1!`; `create_app(seed=False)` + module `app = create_app(seed=False)`; fixtures only via tests `seed=True` or `WAIKE_SEED_TEST_FIXTURES=true` (blocked in bare production); `waike-hub bootstrap-admin` one-time first admin; login requires `site_id`; multi-role `Actor.has_role` + precedence; atomic validate-before-mutate `create_user`.
- PR2 assessment lifecycle preserved under real identity (forward migration m003; fixture auth only behind explicit test config).
- Authoritative CI: `.github/workflows/pr3.yml` includes **startup-security** gate (`DEFAULT_RUNTIME_HAS_NO_TEST_ACCOUNTS`, `DEFAULT_RUNTIME_FIXTURE_AUTH_DISABLED`, `DEFAULT_RUNTIME_PRODUCTION_AUTH_ENABLED`).

## Test plan
- [ ] Remote CI required jobs green including **startup-security** and verify-pr3
- [ ] Confirm default `create_app()` / module app: zero synthetic users; production auth on; fixture auth off
- [ ] Confirm bootstrap-admin creates only requested site/admin; second call does not overwrite password
- [ ] Confirm login requires site_id; cross-site username isolation
- [ ] Confirm multi-role membership authz + atomic create-user negatives
- [ ] Confirm macOS artifact name `waike-learning-os-pr3-macos-<short-head>`
- [ ] Owner review + merge (do not auto-merge)

## Claim boundary
Earned only after remote CI green on final head: `MULTI_USER_LMS_ALPHA_DIGITALLY_COMPLETE` / `PR3_READY_FOR_OWNER_REVIEW`.
Does **not** claim human/field/a11y/security certification or Wave 4 offline sync.
