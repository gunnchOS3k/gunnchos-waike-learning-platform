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

## Closure pass findings (second adversarial round)

The first round reviewed the server contract. This round reviewed whether the
shipped client actually exercises it, and whether authorization holds for an
attacker who is a legitimate user of the same site.

| ID | Severity | Area | Finding | Resolution |
|----|----------|------|---------|------------|
| B1 | merge-blocking | honesty | Offline state was hard-coded in `App.tsx` (`pendingSyncCount=0`, `syncing=false`, `ackPersisted=false`); the Python `OfflineDevice` proved only the server contract, never the shipped client | Fixed: `offline.rs` native store + Tauri commands + `syncCoordinator.ts` + `useOfflineSync`; banner renders real counts. Rust encrypted-DB tests and TS coordinator tests against a real HTTP hub |
| B2 | merge-blocking | authz | Authorization tested `is_instructor_side` / same-site, so an unrelated instructor in the same site could reach another section's attempts, leases, receipts and moderation | Fixed: `SectionService.require_section_access` / `require_staff_scope` / `require_learner_enrollment`; every activity and sync entry point resolves the object's section first |
| B3 | merge-blocking | integrity | Idempotency keyed on `client_mutation_id` alone, so a stolen id replayed by another actor returned the original receipt | Fixed: `_assert_idempotent_match` compares actor, site, section, entity, operation and payload hash; mismatch is `MUTATION_ID_REUSE_MISMATCH` (409) and never returns the other actor's receipt |
| B4 | merge-blocking | tenancy | Attachment dedup was global on `content_hash` and path containment used `startswith` | Fixed: unique `(site_id, content_hash)`; `Path.resolve().relative_to(root)` containment; quarantined blobs are retained as evidence rather than dropped |
| B5 | merge-blocking | integrity | Quiz timing trusted client-reported elapsed time | Fixed: server stores `deadline_at` from server start + accommodation; late work is stored as `timed_out` evidence and is not auto-graded as valid |
| B6 | merge-blocking | integrity | Manual grading mutated before validating, so a nonexistent item could be graded into existence and out-of-bounds/non-finite points were accepted | Fixed: validate-before-mutate inside a savepoint; audit records before/after |
| B7 | merge-blocking | security | LOCAL_SOFTWARE labs accepted learner-supplied evidence hashes | Fixed: `lab_runner` executes a server-fixed trusted fixture id in a temp workdir with scrubbed env, timeout and output cap; evidence hashes are computed server-side and a forged learner hash cannot replace them |
| B8 | merge-blocking | integrity | A rejected or conflicted mutation could leave partial domain writes because sub-services committed independently | Fixed: `txn` module tracks savepoint depth so nested services never commit or roll back an outer transaction; ledger row survives while domain writes roll back |
| B9 | non-blocking | tenancy | `seed_section_activities` used globally fixed quiz/item/lab ids, so a second section would have been handed the first section's quiz | Fixed: seeded ids are section-scoped; the demo section keeps its historical ids |
| B10 | non-blocking | honesty | Two tests could silently pass without asserting (a `pytest.skip` when the seed had one quiz, and an early `return` when no answer-key button rendered) | Fixed: both now seed what they need and always assert; the verifier blocks on any skipped Python test |

## Accepted, documented trust boundaries

These are limits of the implementation, stated rather than hidden:

- The lab runner is process-level confinement (fixed interpreter, fixed command,
  temp workdir, scrubbed env, wall-clock timeout, output cap). It is not an OS
  sandbox, and the lab spec says so in `safety_notes`.
- High-integrity timed quizzes are not trusted offline. Without a signed
  deadline the client clock is advisory only, and an attempt synced after the
  server deadline is recorded as `timed_out`.
- Hardware lab evidence remains external and is never synthesized.

## Merge-blocking open

**Zero** after the fixes above (A1–A5, B1–B8).

## Test honesty

- Synthetic fixtures only via `seed=True` / tests
- No fabricated hardware evidence
- Remote CI claim withheld until green on final head
