# Gate C: Interoperability, Device OS integration, and hardening

## Summary
- OneRoster pilot subset (orgs/users/courses/classes/enrollments) import/export + sabotage suite
- QTI subset matching Gate A quiz engine + XXE/ZIP/HTML security
- LTI 1.3 foundation (registration, OIDC state/nonce, JWT/JWK, role mapping) — **not certified**
- Device OS digital bridge against accepted main `28562a8` — launcher/permissions/deep-links/capability/update/continuity; Device Quartet digital profiles
- Hardening: backup/restore integrity, migration ladder m006, package lifecycle, admin, privacy (no FERPA claim), sabotage, rate limits, a11y + keyboard E2E, observability redaction, performance/concurrency

## Claims sought (when CI green)
- `INTEROPERABILITY_AND_DEVICEOS_DIGITAL_INTEGRATION_COMPLETE`
- `PLATFORM_HARDENING_DIGITALLY_COMPLETE`

## Cross-repo
- Device OS PR: **not required** (consume accepted main)
- WAIKE maintenance PR: **not required**

## Test plan
- [ ] Gate C workflow green on PR head
- [ ] `make verify-gate-c` PASS
- [ ] Prior-gate regression green
- [ ] Native Linux/macOS unsigned artifacts uploaded
- [ ] Owner review; **do not auto-merge**

## Honesty
Does not claim certifications, physical Device Quartet, FERPA, production signing, or Gate D.
