# Gate A Adversarial Review

Structured adversarial pass (architecture / security / authz / offline / UX / a11y / test-honesty).

## Findings

| ID | Severity | Area | Finding | Resolution |
|----|----------|------|---------|------------|
| A1 | merge-blocking | authz | Lease after enrollment revoke still usable | Fixed: assert_lease_allows checks active enrollment / USER_DISABLED |
| A2 | merge-blocking | security | Answer key available to learners | Fixed: learner quiz view omits keys; `/answer-key` instructor-only |
| A3 | merge-blocking | integrity | Synced UX before durable ack | Fixed: OfflineDevice + Rust persist_sync_ack require receipt JSON first |
| A4 | merge-blocking | security | Path traversal on attachments | Fixed: reject `/`, `\\`, `..`; quarantine status |
| A5 | merge-blocking | honesty | Hardware evidence fabrication | Fixed: HARDWARE_EVIDENCE_FABRICATION_FORBIDDEN |
| A6 | non-blocking | ux | Full offline pack mirror UI incomplete | Accepted for Gate A digital scope; sync banner + outbox present |
| A7 | non-blocking | a11y | Not a certification | Documented; automated smoke only |

## Merge-blocking open

**Zero** after fixes above.

## Test honesty

- Synthetic fixtures only via `seed=True` / tests
- No fabricated hardware evidence
- Remote CI claim withheld until green on final head
