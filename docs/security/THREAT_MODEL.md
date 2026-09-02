# Threat model (PR 1)

## In scope for PR 1 controls

| Threat | Control |
|--------|---------|
| Learner-key leakage | No production private keys committed; test keys marked `TEST_ONLY`; learner packs must not embed signing/decryption secrets |
| Instructor impersonation | Instructor packs are separate encrypted artifacts; learner install path rejects `role=instructor` |
| Cross-role data access | Compiler split + security tests forbidding solutions/keys in learner packs |
| Malicious/corrupted course packages | Ed25519 verify + per-file SHA-256 before trust |
| Downgrade attack | Compatibility policy rejects lower protected content/schema versions |
| Prompt injection through course content | Content treated as untrusted data until verified; UI renders as documents, not executable policy; future tutor runtime must sanitize |

## Documented future domains (not implemented in PR 1)

| Threat | Boundary |
|--------|----------|
| Autograder escape | No autograder runtime in PR 1; future sandboxes required |
| Offline-device theft | File encryption helps at rest; full device policy belongs to Device OS later |
| Sync replay | No sync protocol in PR 1 |
| Grade tampering | No gradebook in PR 1 |

## Explicit non-claims

PR 1 automated tests do not equal a production security review.
