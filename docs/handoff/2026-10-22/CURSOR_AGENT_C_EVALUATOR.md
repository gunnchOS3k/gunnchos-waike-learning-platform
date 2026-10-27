# Cursor Agent C evaluator — 2026-10-22

Official V1.0.0 is **NOT READY** and **NOT AUTHORIZED**. RC2 is **NOT READY** and **NOT AUTHORIZED**. Blocker **B03 is not fixed**. A client authorization filter is not a grade.

The practice-evaluator pass stays in `docs/handoff/2026-10-22/CURSOR_AGENT_C_ANCESTRY.md` under “Evaluator pass”. That note was not deleted and that test was not rerun. This file only adds the next existing case.

## Answer-key authorization

Head at the start of this pass was still `f1bc887ca79145bab9d0764c134e7ece1d07b838` on `eng/cursor-v1-agent-c-learn`. It was not reset. No product code changed.

Existing test: `apps/client/src/lib/product/product.test.ts`, case `denies answer keys and other sections`.

Command, from `apps/client`, existing vitest `v2.1.9` (symlink into `_waike_full_delivery`, not committed):

`./node_modules/.bin/vitest run src/lib/product/product.test.ts -t "denies answer keys and other sections" --reporter=verbose`

Result: **pass**. `Test Files  1 passed (1)`. `Tests  1 passed | 32 skipped (33)`. Start `23:18:12`. Duration `858ms`. Exit code 0.

The case marks `Week 1 answer key` as answer-key material. For a learner limited to `sec_sb`, `authorizeSearchHits` keeps the lesson hit in that section and drops the instructor answer-key hit and the hit in `sec_other`. That is a client search filter. It does not grade, does not authorize a live instructor, and does not call an evaluator.

Pins were not changed. Stack `curriculum/registry/PIN.json` `pinned_commit` and `authoritative_pin_commit` remain `33a101852f4fefb0eb239bcffa60a65d71102e2c`. `previous_pinned_commit` remains `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62`. Workflow checkouts for gates B–D and windows-pilot0 remain `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62`. `origin/main` remains `2641042936f3b965daccb11091c80cbc6fa64f91`. `f668ea40` was not cherry-picked onto main. Draft pull request #29 stays https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/29.

Disk at this pass: about 12 GiB free on `/System/Volumes/Data`, still under the 18 GiB reserve. No npm install. No TLS bypass. No production gunnchAI call. No trusted replay.

V1 and RC2 remain **NOT READY**. B03 stays open.

Next dependency that stops this lane: a live evaluator still needs an authorized localhost CA and leaf. Do not attempt trusted replay. Do not bypass TLS and do not call production gunnchAI.
