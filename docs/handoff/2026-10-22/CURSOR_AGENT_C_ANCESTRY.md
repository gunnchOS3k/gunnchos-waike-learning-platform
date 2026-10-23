# Cursor Agent C ancestry — 2026-10-22

Official V1.0.0 is **NOT READY** and **NOT AUTHORIZED**. RC2 is **NOT READY** and **NOT AUTHORIZED**. Blocker **B03 is not fixed**. A persisted lesson-read flag is not a grade.

This note records ancestry, a blocked focused cherry-pick, and the curriculum-pin discrepancy. It does not split pull request #29 into a one-commit release candidate.

## Checkout

| Item | Value |
|---|---|
| Repo | `gunnchOS3k/gunnchos-waike-learning-platform` |
| Worktree kept | `repos/gunnchos-waike-learning-platform/.worktrees/cursor-v1-agent-c-learn` |
| Branch pushed | `eng/cursor-v1-agent-c-learn` |
| Draft PR #29 | https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/29 |
| #29 state | open draft; left open |
| #29 head before this note | `d2fde4177a9de0686e265ba74c0539aa0e9f541f` |
| Live `origin/main` | `2641042936f3b965daccb11091c80cbc6fa64f91` |
| Reported lesson-read base | `6bdfa0b416ea95b0abb36669faa8059095962281` |
| Commits on #29 before this note | 16 ahead of `origin/main` |

`origin/main` was fetched during this pass and is still `2641042936f3b965daccb11091c80cbc6fa64f91`. That matches the PR base. The 16-commit range includes the older delivery stack. It is not a minimal release candidate.

## Which commits are the lesson-read fix

The localStorage round-trip is one commit:

| SHA | Role |
|---|---|
| `f668ea40a32c3d991a7ba42d9be5d836356b1dbb` | Lesson-read fix and the test. Touches only `apps/client/src/components/learner/BrowserLearning.tsx` and `BrowserLearning.test.tsx`. |
| `eb229afd13e4aa7d01a3c40a022c38d3fbac250b` | Prior handoff note. Docs only. Not the fix. |
| `d2fde4177a9de0686e265ba74c0539aa0e9f541f` | Prior note that records the draft PR. Docs only. Not the fix. |

Older delivery commits, parent through `6bdfa0b416ea95b0abb36669faa8059095962281`, are unrelated to the localStorage round-trip:

1. `f15795b7d4e8e64e2430d19fe6c62d40feb97abd` — full browser reader, protected practice evaluation, guest evidence
2. `220f5e1ae6dc1b40225a0ae91d89232310332cbd` — bind reader and compiler to continuation source
3. `8a1d8bb90eb866afa025f5063cd96af2bd5235b6` — assessment and build logs
4. `f4e71d7310a30d189a3cf59e68ab9d2440892a0f` — delivery provenance after CIDR correction
5. `f15667ccc79dec713d1661921cba5705c269512d` — Digital Confidence case evaluation
6. `b435600c5d3ba994856292c15a0435e6b90f7dea` — ten-week Digital Confidence reader
7. `1e133e8876a444835f3ca90598aae018badff89a` — WFD-2 learner delivery package
8. `0668da932ed4b1aa5be0ff22cf0a56a7906551f4` — import declarations
9. `c6b9362f3426852467bec557a93ba578cb958a73` — same-origin Hub deployment
10. `025e1002a611e4ece6465ac6a2176bfc90675ba2` — course export and runtime checkpoint
11. `32731aeec37ee3bf780736691bda2b3d2ea9a987` — same-origin HTTPS demo record
12. `c7d1aefd9a641e99c8cf1746c9d6eef841a3096f` — practical file-read race
13. `6bdfa0b416ea95b0abb36669faa8059095962281` — refresh of that demo; base of the lesson-read commit

## Focused candidate is blocked

A worktree `cursor-v1-agent-c-learn-focused` was created from `origin/main` at `2641042936f3b965daccb11091c80cbc6fa64f91`. Cherry-pick of `f668ea40a32c3d991a7ba42d9be5d836356b1dbb` stopped with:

`CONFLICT (modify/delete): apps/client/src/components/learner/BrowserLearning.tsx deleted in HEAD and modified in f668ea4`

`CONFLICT (modify/delete): apps/client/src/components/learner/BrowserLearning.test.tsx deleted in HEAD and modified in f668ea4`

`origin/main` has `apps/client/src/components/LessonReader.tsx`. It does not have `BrowserLearning.tsx` or `BrowserLearning.test.tsx`. The cherry-pick was aborted. The empty focused branch was removed so it would not be mistaken for a candidate. The old worktree was not destroyed. The delivery stack was not rebased onto main.

Safe integration remains the existing review path for #29. #29 must stay labeled as a stack, not a one-commit fix. No focused pull request was opened.

## Provenance

No pin was changed. The two SHAs are different generations of `waike-research-ops`. Equating them would either mislabel the baked reader or point CI at a commit GitHub cannot fetch.

| SHA | Repo | Where it is recorded | Exists | Branch / reachability |
|---|---|---|---|---|
| `33a101852f4fefb0eb239bcffa60a65d71102e2c` | `waike-research-ops` | Learning-platform `curriculum/registry/PIN.json` `pinned_commit` and `authoritative_pin_commit` on this stack. Also `sourceCommit` in `apps/client/src/generated/publicCurriculumContent.json` and the public curriculum chunks, and `artifacts/full-delivery/production/runtime-release.json` `curriculum_commit`. | Local `git cat-file -t` is `commit`. GitHub API returns 422, no commit for that SHA. | Local branch `delivery/full-learning-2026-10-15` contains it. Not an ancestor of `origin/main` (`34ae043abbd38c89bd30f7ae1ae7cf8cc06645a0`). Message: "Record dated-source audit and synchronized canonical evidence" (2026-10-15). |
| `63ba9f25ac6b8d8d1b6dd118923566fd51c57b62` | `waike-research-ops` | Workflow input. `WAIKE_PIN_REF` in `.github/workflows/gate-b.yml`, `gate-c.yml`, `gate-d.yml`, and `windows-pilot0.yml` checks out `gunnchOS3k/waike-research-ops` at this ref. Gate C then requires `curriculum/registry/PIN.json` `pinned_commit` to equal that checkout (`PROVENANCE_MISMATCH` otherwise). Also the default in `scripts/verify_gate_c.py`, `scripts/verify_gate_d.py`, `scripts/clean_room_reconstruct.py`, and `tests/gate_b/test_compiler_18.py`. On `origin/main`, `PIN.json` `pinned_commit` is this SHA. | Local `commit` and GitHub commit https://github.com/gunnchOS3k/waike-research-ops/commit/63ba9f25ac6b8d8d1b6dd118923566fd51c57b62 | Ancestor of `origin/main`. Also on `origin/curriculum/pr59-ci-depth-quality-closure`. Message: "Refresh readiness artifact SHAs to child tip after CI/depth closure." (2026-09-20). |

`63ba9f25` is an ancestor of `33a10185` (24 commits). `curriculum/taxonomy/eighteen_tracks.json` and `artifacts/taxonomy/CANONICAL_TRACK_REGISTRY.export.json` are the same blobs at both commits. Fifty-one `lesson.md` files differ. The baked Networking week-1 lesson `f07d07ef3ecd3b283694f9683009f40d733388305fe9706b2d3a54774555f0de` matches `33a10185` and differs from `63ba9f25` (`ad2bb3daf72f833c2d61f03ec9529f5e2014434ef1eb79d736e4b0a6845d2df0`). The reader identity on this stack is `33a10185`. The workflow identity is `63ba9f25`.

`PIN.json` on this stack already names `63ba9f25` as `previous_pinned_commit`. That is the right split. Retargeting `pinned_commit` to `63ba9f25` would make the Gate C comparison pass and would mislabel the baked lessons. Retargeting `WAIKE_PIN_REF` to `33a10185` would fail checkout because that commit is not on GitHub. No third pin was invented. The local ops tip `18efa764e4db066fb17d597284557195499f93ea` is one commit past `33a10185` on `delivery/full-learning-2026-10-15` and was not recorded as a pin. `waike-research-ops` working tree was not edited. `gunnchAI3k/.worktrees/waike-lp-stream-b` was not deleted.

## Learner journey

Evidence level this pass: **grade percent suppressed when weighting is not modeled**. Not a complete learning experience. Not a grade.

Command, from `apps/client`, existing vitest binary (symlink to `_waike_full_delivery/platform/apps/client/node_modules`, not committed):

`./node_modules/.bin/vitest run src/lib/product/product.test.ts -t "hides overall percent when weighting is not modeled"`

Result: 1 passed, 32 skipped, 0 failed. `overallPercentAllowed` returns null when `weightingModeled` is false.

Not run: lesson-read vitest (already recorded on `f668ea40`; this pass did not recreate it), practice evaluator, instructor auth, Gallery publication, offline Hub sync, gunnchAI provider. No production gunnchAI call. No fake provider success.

Blocking dependencies: `BrowserLearning` is not on `origin/main`; free disk is about 12 GiB, under the 18 GiB reserve, so no npm install; trusted TLS replay was not attempted.

## TLS and untouched surfaces

TLS is unchanged. No certificate was injected. No TLS bypass.

Not edited: anime-aggressors, PartyLink, beatlink-party, the website, Codex art, gunnchos-research-portal, waike-research-ops, gunnchAI3k.

Disk at this pass: about 12 GiB free. No heavy install. The failed focused worktree was removed after the abort.

## Next executable learning task

Keep #29 in review as the delivery stack that contains the reader. Do not cherry-pick `f668ea40` onto main until `BrowserLearning` exists there. Do not retarget either curriculum pin. The next learning proof, after that stack is the review surface, is an existing evaluator or instructor-auth test inside the delivery tree, still without a TLS bypass and without a production gunnchAI call.
