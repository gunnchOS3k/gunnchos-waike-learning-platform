# CX0 Education Standards Architecture (DRAFT)

**Status:** Architecture + backlog only. `certification_claimed: false`  
**Base:** origin/main `b1c3ab5` — does not disturb Device Lab accepted-main pin.

## Existing (keep)

| Standard | Status | Location |
|----------|--------|----------|
| LTI 1.3 | PARTIAL digital | `services/hub/app/modules/lti.py` |
| QTI 3 subset | PARTIAL digital | `services/hub/app/modules/qti.py` |
| OneRoster pilot | PARTIAL digital | `services/hub/app/modules/oneroster.py` |

## Target additions (ABSENT → planned)

| Standard | Role | Mapping |
|----------|------|---------|
| CASE 1.1 | Competencies/outcomes | Curriculum outcomes → CASE CF documents |
| Caliper 1.2 | Learning analytics events | Activity engine events → Caliper envelopes |
| Open Badges 3.0 | Assertions | Future CredentialRecord issuer |
| CLR 2.0 | Comprehensive learner record | Portfolio aggregation |
| Edu-API (optional) | Roster/gradebook API | Parallel to OneRoster pilot |

## Claim boundary

- Schemas/adapters here are **conformance-safe drafts** from public specs.
- Schema presence ≠ certification.
- No changes to Gate C/D matrices in this PR beyond documentation pointers.
- Device Lab Hub bind remains release-train owned.

## Backlog

1. CASE competency document adapter (read-only import)
2. Caliper event exporter (opt-in, privacy-gated)
3. OB3 + CLR CredentialRecord store (domain 10)
4. Edu-API exploratory spike after OneRoster stability
