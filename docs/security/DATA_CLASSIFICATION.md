# Data classification

| Class | Examples | PR 1 handling |
|-------|----------|---------------|
| Public curriculum | Lesson plans, student workbooks | May appear in signed learner packs |
| Instructor-protected | Solution guides, teaching notes, answer keys | Encrypted instructor pack only |
| Test secrets | `TEST_ONLY_*` keys | Fixtures only; never production |
| Production secrets | Signing keys, hub credentials | **Not present** in PR 1 |
| Pilot PII / grades / submissions | Live learner records | **Not collected** in PR 1 |

Protected pilot data must never be committed to this public repository.
