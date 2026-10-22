# Cursor Agent C learn handoff — 2026-10-22

Official V1.0.0 is **NOT READY** and **NOT AUTHORIZED**. RC2 is **NOT READY** and **NOT AUTHORIZED**. Blocker **B03 is not fixed**. Blocker **B08 is unchanged**. No production deploy, no minors rollout, no institutional launch, no human approval, and no TLS bypass.

This packet is a draft engineering note. A unit-1 browser read is not 18-track assessment, offline, integration, or education acceptance.

## Checkout

| Item | Value |
|---|---|
| Repo | `gunnchos-waike-learning-platform` |
| Worktree | `repos/gunnchos-waike-learning-platform/.worktrees/cursor-v1-agent-c-learn` |
| Branch | `eng/cursor-v1-agent-c-learn` |
| Base (local delivery tip, not `origin/main`) | `6bdfa0b416ea95b0abb36669faa8059095962281` |
| Fix commit | `f668ea40a32c3d991a7ba42d9be5d836356b1dbb` |
| `origin/main` | `2641042936f3b965daccb11091c80cbc6fa64f91` |

`origin/main` does not contain `BrowserLearning.tsx`. The reader lives on the local delivery line. This branch therefore contains those preexisting delivery commits plus the fix commit and this handoff. They are not a release candidate.

Read-only SHAs, not edited:

| Repo | SHA | Note |
|---|---|---|
| `waike-research-ops` | `dd1c5ae0a917ce3fc45e7def2439cc6981bf0ab7` | Dirty main checkout left untouched. Canonical matrix read from `curriculum/taxonomy/eighteen_tracks.json`. All 18 `owner_program_file` paths exist. |
| `gunnchAI3k` | `e64d3dbca9ab821b5d40c7c981b723201c0307c8` | Dirty checkout left untouched, including the 1-byte `src/tutor/*` working tree and untracked `.worktrees/waike-lp-stream-b`. |
| `3k-mlv` revival worktree | `5e99c64673557efe7cbdfbbfb4d4ebcdcabfaab7` | Read only. No `node_modules`. B08 not changed. |

No `AGENTS.md` was present in the learning-platform worktree, `waike-research-ops`, or the gunnchAI3k checkout that was inspected.

Disk at start: about 15 GiB free, under the 18 GiB reserve. No npm install. Vitest was the existing binary, reached through a local symlink to `_waike_full_delivery/platform/apps/client/node_modules`. That symlink is untracked and must not be committed.

## 18-track matrix

Source: `waike-research-ops` `curriculum/taxonomy/eighteen_tracks.json` (`waike.taxonomy.eighteen_tracks.v1`). The reader `PUBLIC_TRACKS` list matches these ids in this order. None were invented.

Learner step that actually ran: render unit 1 and press **Mark this lesson read**. The page then showed `Lesson reads: 1` and `Course completion: not established`. The practice evaluator was not called. No grade, completion, or competency was written.

| id | client unit-1 read | why |
|---|---|---|
| DIGITAL_CONFIDENCE | verified | Unit 1 rendered and marked read. Practical component is also on this track; the existing file-read test passed. Not a Hub grade. |
| IT_SUPPORT_HARDWARE | verified | Same client step. Unit-1 lesson markdown SHA-256 prefix `3940c2b0a8a9` matches DIGITAL_CONFIDENCE. Coursework was not rewritten. |
| SOFTWARE_BUILDER | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| NETWORKING_INFRA | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| CYBER_SOC | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| DATA_DASHBOARDS | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| AI_ML_EDGE | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| EMBEDDED_PROTOTYPING | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| WIRELESS_6G | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| PM_AGILE_LSS | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| GAME_DEV_INTERACTIVE | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| SEVEN_GC_APPRENTICESHIP | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| CLOUD_DEVOPS | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| COMM_PD_ETHICS | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| ROBOTICS_CONTROL | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| GUNNCHOS_PRODUCT_LAB | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| HARDWARE_ENGINEERING | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |
| DATA_VIZ_BI | verified | Unit 1 rendered and marked read. Completion stayed unestablished. |

Not verified for any track: authenticated assessment submit, offline Hub sync, instructor review, or education acceptance. Each unit-1 quiz payload has 6 items on disk. Those items were not sent to an evaluator.

## Defect

Not the Lessons→Home repair. That repair remains `7b9484f` on `fix/public-lessons-navigation-2026-10-19` and was not edited.

`BrowserLearning` `save()` updates in-memory `record.viewed` immediately. It writes `localStorage` only when device saving is already on. The “Save practice on this browser” checkbox set that flag and, when turned off, deleted storage. Turning it on did not write the current record. A remount therefore read nothing back.

Before the fix, `vitest run src/components/learner/BrowserLearning.test.tsx -t "reads lesson progress back"` failed in `BrowserLearning.test.tsx` while waiting for `Lesson reads: 1` after remount. The earlier assertions in that test had already seen the in-memory count and `localStorage.length === 0`.

Fix: when the learner turns device saving on, write the current practice record, and when they turn it off, keep removing it. Coursework text, the privacy copy on the checkbox, and instructor authority are unchanged. The evidence line still says course completion is not established. No grade, completed lesson, or assistant answer was fabricated.

## Tests

Command, from `apps/client`, using the existing vitest binary:

`./node_modules/.bin/vitest run src/components/learner/BrowserLearning.test.tsx src/components/learner/DigitalConfidencePractical.test.tsx`

After the fix: 2 files passed, 7 tests passed, 0 failed.

## gunnchAI

Not run. No production provider call. No new fake provider. `gunnchAI3k` has no `node_modules`. The dirty tutor files were left as they were. Committed `src/local-runtime/discovery.ts` already records an ollama miss or list failure as notes and keeps the fixture provider primary. That path was not executed.

## TLS

Unchanged. `docs/release/campaigns/2026-10-19/continuations/trusted-replay/REPORT.md` on the portal coordination tree still has `TRUSTED_TLS_PASS` false. The recorded localhost certificate is self-signed and expired. No CA or leaf was installed, no private key was embedded, and verification was not bypassed. Trusted replay did not run.

## Not touched

anime-aggressors, PartyLink, beatlink-party, pedestrian-pursuit, archive-of-life-artifact-world, the research portal (including `BLOCKERS.json`), Codex art, and the production website. No invitation server was added.

## Next executable learning task

Owner provisions an authorized current localhost CA and leaf (DNS:localhost SAN, current validity, chain into the browser trust store, key mode 0600). Then run one trusted same-origin replay of a single fictional learner practical and stop. Do not mark B03 fixed. Do not treat this unit-1 read as the 18-track acceptance gate.
