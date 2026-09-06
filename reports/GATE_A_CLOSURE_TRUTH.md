# Gate A Surgical Closure — Truth Report

Scope: close the gaps found when Gate A (PR #4) was re-examined against what the
shipped client and server actually do, rather than what the server contract
tests alone proved. No Gate B work. No test weakened.

Branch: `cursor/waike-learning-gate-a-offline-activities`
Base: `4e0afbe44bd595da6f44aebb465dea891ace629b`
WAIKE pin: `e97e74fc9bfb44b1cdc26b272dc4848264f15fe0`

## What was actually wrong

The original Gate A work had a real server, a real migration and a real test
suite, but three kinds of gap:

1. **The client did not use it.** `App.tsx` displayed literal constants for the
   offline state. The Python `OfflineDevice` in the test suite simulated a
   client well enough to prove the *server contract*, which meant the suite
   stayed green whether or not the Rust store and the React app were wired at
   all.
2. **Authorization asked the wrong question.** Checks were role-shaped
   (`is_instructor_side`, same site) rather than object-shaped. An instructor
   legitimately logged into the site could reach a section they were never
   assigned to.
3. **Several server paths trusted the client** for things only the server can
   know: elapsed quiz time, lab evidence hashes, and the meaning of a reused
   mutation id.

## Closure by area

### 1. Native offline wiring

`apps/client/src-tauri/src/offline.rs` is the native store inside the existing
encrypted database: cached leases (cache, read, list, mark revoked, mark
expired) and a durable sync outbox (enqueue, next local sequence, list pending,
list by status, update state, persist ack, counts, aggregate offline state).
State transitions are validated in Rust — unknown and terminal transitions are
refused, and an acknowledgement is refused unless the receipt was persisted
first.

`lib.rs` exposes these as Tauri commands. There is no arbitrary-SQL command;
each command is a named operation with typed arguments.

`apps/client/src/lib/offline/syncCoordinator.ts` drives the lifecycle: take a
lease while online, store it natively, enqueue mutations while offline, and on
restart read the queue back out, POST `/api/v1/sync/mutations`, persist the
receipt locally *before* marking the item acknowledged, then classify
conflict / rejected / quarantined / retryable and pull changes.
`useOfflineSync` exposes that to React, and `SyncStatusBanner` renders the real
counts — it cannot show "synced" while anything is pending or an ack is not
durable.

The Python `OfflineDevice` tests are kept as server-contract tests. The native
path is now covered separately by Rust tests against a real encrypted database
and by TypeScript tests against a real HTTP hub.

### 2. Object-level authorization

`SectionService` gained `require_section`, `has_staff_scope`,
`require_staff_scope`, `require_learner_enrollment`, `require_section_access`
and `require_learner_or_staff_for`. Staff must be *assigned* to the section;
learners must be *actively enrolled*.

`SyncService` and `ActivityEngine` resolve the object first and then authorize
its section. `apply_mutation` authorizes even when no lease is presented.
`pull_changes` requires authorized access, so a revoked learner cannot pull.
Lease read and revoke require ownership or assigned staff/admin — an unrelated
same-site instructor is denied. `sync_receipts` carries `site_id` and
`section_id` so receipt reads can be scoped the same way.

### 3. Idempotency

A replay is honoured only when actor, site, section, entity type, entity id,
operation and payload hash all match the stored mutation. Anything else is
`MUTATION_ID_REUSE_MISMATCH` with 409. A receipt belonging to another actor is
never returned.

### 4. Attachment tenancy and paths

Containment uses `Path.resolve().relative_to(root)`, not string prefixes.
Dedup is unique on `(site_id, content_hash)`, so an identical file in another
site is a separate blob and cross-site reads are impossible. The persisted
section is authorized before the write. A blob that fails MIME policy is
recorded as `quarantined` rather than silently dropped, so the evidence
survives without being treated as accepted work.

### 5. Quiz timing

The server writes `deadline_at` at attempt start from the server clock plus the
learner's accommodated duration, with a small fixed grace. Client-reported
elapsed time is advisory. A submission past the deadline is stored as
`timed_out` evidence and is not auto-graded as valid work.

Trust boundary: high-integrity timed quizzes are not trusted offline. Without a
signed deadline the offline client cannot be relied on for timing, so an
attempt that arrives late through delayed sync is recorded as `timed_out`.

### 6. Manual grading integrity

Grading validates before it mutates: authorization, attempt exists and is in a
gradable state, item exists and belongs to that attempt's quiz and is
manual-eligible, points are finite and in bounds, and the learner/site/section
are consistent. A nonexistent item cannot be graded into existence, an
objective item cannot be hand-graded, and an attempt is not marked fully graded
while required manual items remain. Before/after values are audited.

### 7. LOCAL_SOFTWARE lab runner

`lab_runner` runs a trusted fixture named by the lab definition
(`runner_id`), not anything the learner supplies. The learner supplies data
only. Execution happens in a temporary work directory with a scrubbed
environment, a wall-clock timeout and an output cap, and the evidence hashes
are computed server-side from the captured output. A forged learner hash cannot
replace the computed one.

Trust boundary: this is process-level confinement, not an OS sandbox, and the
lab spec says so. Hardware lab evidence remains external.

### 8. Production activity UX

`LearnerActivities` and `InstructorActivities` are real screens on the PR3
session auth, not debug JSON dumps. Learners get quizzes, labs, discussions,
groups and their own accommodation note. Instructors get the manual grading
queue, next ungraded, answer keys, discussion moderation, group inspection,
accommodations and submission-scoped regrade. The learner client has no answer
key call at all.

### 9. Migration m004

Foreign keys to `users` / `sites` / `sections`, CHECK constraints on statuses
and enumerated types, `(site_id, content_hash)` uniqueness on attachment blobs,
`site_id` / `section_id` on `sync_receipts`, `deadline_at` and
`effective_time_limit_minutes` on attempts, server-computed evidence columns on
lab runs, and supporting indexes. The PR3 → Gate A migration test stays green.

### 10. Transaction integrity

`txn` tracks savepoint depth per connection so a nested service never commits
or rolls back an outer transaction. A rejected or conflicted mutation rolls
back its domain writes while the ledger row that records the rejection
survives. Tests assert no partial rows after rejection, conflict, unauthorized
attempts and failed grading, and that no savepoint is left open after a mixed
batch.

## Evidence

| Suite | Where | Tests |
|-------|-------|-------|
| Python, whole repo | `tests/`, `services/hub/tests` | 204 passed, 0 skipped |
| Python, Gate A | `tests/gate_a` | 99 collected |
| Closure: object authz | `test_object_authz_closure.py` | 11 |
| Closure: idempotency | `test_idempotency_closure.py` | 8 |
| Closure: attachment tenancy | `test_attachment_tenancy_closure.py` | 8 |
| Closure: quiz timing | `test_quiz_timing_closure.py` | 8 |
| Closure: manual grading | `test_manual_grading_closure.py` | 10 |
| Closure: lab runner | `test_lab_runner_closure.py` | 10 |
| Closure: transaction integrity | `test_transaction_integrity_closure.py` | 7 |
| Rust, encrypted store | `cargo test` | 11 passed (6 in the offline store) |
| TS unit + a11y | `pnpm test` | 30 passed |
| TS against a real hub | `pnpm test:live` | 19 passed |

The live TypeScript suites run against a seeded FastAPI hub started over real
HTTP by `scripts/run_test_hub.py`, with production auth on and fixture header
auth off, so the client must log in for real.

## Test honesty

- Zero skipped Python tests. The verifier treats a skip as an unproven claim
  and blocks on it.
- No `continue-on-error` and no `|| true` in the Gate A workflow.
- The two tests that could previously pass without asserting were fixed to seed
  what they need and always assert.
- No fabricated hardware evidence.
- The Gate A claim is withheld until remote CI is green on the final head.

## Not in scope

Gate B (gunnchAI and the 18 WAIKE tracks) was not started. Human/field
validation, accessibility certification and security certification are not
claimed.
