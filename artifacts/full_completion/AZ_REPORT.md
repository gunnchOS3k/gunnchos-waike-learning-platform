# WAIKE Real gunnchAI Final Closure — A–Z (Agent B)

Captured: 2026-09-21T03:32:15Z
Child tip: 
Parent #21 tip: `8577e15a74edd07df7b3d159a195d8fe57d1c6b5`
Branch: `device-lab/pr21-real-gunnchai-ai-final-closure`
Base: `device-lab/pr20-final-curriculum-ai-pixel-closure`
Device alias: `PIXEL_USB_DEVICE_1`

## A — live #54 head
`851e7916d6d5c7da23a8f30dba6bdfd389daa8ac` (parent draft PR #54).

## B — gunnchAI child branch/PR
`integration/pr54-llamacpp-cli-compat-closure` → draft PR https://github.com/gunnchOS3k/gunnchAI3k/pull/55

## C — llama.cpp detected version
Host probe (Agent A): version 10310 (cb26014d9). Compat adapter routes `-no-cnv` to `llama-completion`.

## D — old invalid flag reproduction
Owned/documented by Agent A (`LLAMACPP_CLI_COMPAT_REPRO.json`).

## E — compatibility fix
Owned by Agent A (`llamacpp_cli_compat.ts` on PR #55).

## F — user-ready 002 result
Candidate artifact claims digital PASS; **CI not green yet** on PR #55.

## G — user-ready 003 result
Candidate artifact claims digital PASS; **CI not green yet** on PR #55.

## H — user-ready 004 result
Candidate artifact claims digital PASS; **CI not green yet** on PR #55.

## I — gunnchAI final CI
`GUNNCHAI_REQUIRED_CI_GREEN=false` (queued/awaiting at capture).

## J — gunnchAI candidate SHA
Pinned live tip `164bdb7e55b6cac305baee49e72ca70795c472c4` (PR #55). Field `exact_candidate_sha_for_waike` also recorded `e246034…` (functional fix ancestor). Never `aa61e9`.

## K — live #21 head
Verified `8577e15a74edd07df7b3d159a195d8fe57d1c6b5`.

## L — WAIKE child branch/PR
https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/22 (draft) · branch `device-lab/pr21-real-gunnchai-ai-final-closure`

## M — fake-provider evidence reclassification
**DONE** → `WAIKE_AI_FIXTURE_SURFACE_PASS=true`. Product AI surface gates cleared pending REAL.

## N — real WAIKE→gunnchAI→Nearby Edge execution
**PARTIAL** — Hub assist with `WAIKE_ALLOW_FAKE_AI=0` returned `provider_id=local-product-service` with `[llama.cpp REAL local inference]`. NearbyEdgeServer up on `:8799` (`on_device_local=false`) but gateway `health=down`; Hub→Nearby execute provenance **not** proven. Journey `pass=false`.

## O — benign tutoring result
API **PASS** (real local-product-service + llama.cpp). CDP Pixel UI not stably earned this wave (service drop under CDP).

## P — assessment guardrail
API probe `looks_refused_or_safe=true` under real provider.

## Q — fallback/unavailable result
Nearby gateway health=down observed honestly; no fake Nearby provenance claimed.

## R — lifecycle result
**NOT RUN** (CDP unstable).

## S — provenance truth
Nearby Mac ≠ on-device = true. Full Hub→NearbyEdge provenance = false. Partial real llama via product-service observed.

## T — serial/evidence redaction audit
**PASS (tip)** — `DEVICE_EVIDENCE_REDACTION_AUDIT.json`; PR #21 body redacted to `PIXEL_USB_DEVICE_1`. Prior history may retain raw serial.

## U — Gate C
Exact-head CI on #22 tip: see checks (do not rely on earlier #21 greens).

## V — Gate D
Exact-head CI on #22 tip: see checks.

## W — device-lab workflows
aarch64 Linux + glibc236 + Windows Pilot 0: see #22 checks.

## X — final completion gate
`WAIKE_FULL_PLATFORM_COMPLETION_CANDIDATE_PASS=false` — REAL Nearby Edge route incomplete + Agent A CI not green. Human gates + MERGE_AUTHORIZED false.

## Y — draft PR URLs
- Parent #21: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/21
- This child #22: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/22
- gunnchAI #54: https://github.com/gunnchOS3k/gunnchAI3k/pull/54
- Agent A child #55: https://github.com/gunnchOS3k/gunnchAI3k/pull/55

## Z — remaining human blockers
1. Agent A required CI green on PR #55.
2. Full Hub→Nearby Edge execute provenance on Pixel CDP.
3. Exact-head WAIKE CI green on final child tip.
4. Owner usability + disabled-user a11y validation.
5. Owner merge authorization — **DO NOT MERGE** #20 / #21 / #22 / #54 / #55.

## Owner review checklist — unanswered
```text
[ ] Learner can use the platform end-to-end
[ ] Instructor can use their real role end-to-end
[ ] Grader / Guardian / Site Admin usable
[ ] Disabled-user accessibility human validation
[ ] Authorize merge (explicit)
```
