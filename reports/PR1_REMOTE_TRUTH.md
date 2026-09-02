# PR1 Remote Truth (Gate 0)

Generated during PR1 closure pass. Local `AUTOMATED_PIPELINE_PASS` is not merge authority.

## Observed SHAs (fact)

| Repo | Ref | SHA |
|------|-----|-----|
| waike-research-ops | `origin/main` | `8eb2827dc58ffa391842da1bfb1ee665c25a31a7` |
| waike-research-ops | PR #56 head / local branch tip | `531f194e86b1cb788568de4f7e447316047f80a2` |
| gunnchos-device-os | `origin/main` | `28562a8456207540c205a1c8a6434a491b0a4771` |
| gunnchos-waike-learning-platform | `origin/main` | `187c662a83c0ca2dff97b2c7aaecbde5ba6e4da8` |
| gunnchos-waike-learning-platform | PR #1 head / `origin/cursor/waike-learning-os-pr1-foundation-001` | `6af6ccca21ab6d7e8518ee240e04cd41003708c5` |

## Draft PRs

- WAIKE taxonomy: https://github.com/gunnchOS3k/waike-research-ops/pull/56 — **draft, open**, head `531f194…`, Actions **success**
- Platform PR1: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/1 — **draft, open**, head `6af6ccc…`, Actions **failure**

## `ab9db139` vs `6af6ccc` explanation (fact)

`ab9db1392ef4…` is an **ancestor** on the same PR1 branch (repin/evidence refresh). Later commits landed on the same branch, including `9798d5c…` and tip `6af6ccc…` (“Fix SOURCE_DATE_EPOCH-deterministic learner and instructor pack bytes”). Earlier closure notes that cited `ab9db139…` as “current” were **stale relative to the remote PR head**. Authoritative PR head for this closure pass starts at `6af6ccc…` until a new push updates it.

## GitHub Actions on tip `6af6ccc` (fact)

Latest PR1 workflow run example: `33675330059` — **failure**

| Job | Conclusion | Failure note |
|-----|------------|--------------|
| contracts/compiler | success | |
| hub | success | |
| security | success | |
| frontend | failure | `pnpm install` — `packages field missing or empty` |
| rust | failure | prepare pack / cargo test (Linux deps / compile path) |
| native build linux | failure | `pnpm install` same workspace error |
| verify-pr1 | skipped | upstream failure |

Overlapping `.github/workflows/ci.yml` also fails / masks native build (`continue-on-error`, `|| true`) — divergent CI truth to consolidate.

## WAIKE Actions on tip `531f194` (fact)

CI runs `33674115741` / `33674111505` — **success**.
