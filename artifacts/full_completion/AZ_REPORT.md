# WAIKE Real gunnchAI Final Closure — A–Z (Agent B)

Captured: 2026-09-21T03:32:15Z
Child tip: `f71d1c5dd023b69e6072dc0d3e71d217db5932cf`
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
**CI success** run `35558185933` on `e2d1adc`.

## G — user-ready 003 result
**CI success** run `35558185930` on `e2d1adc`.

## H — user-ready 004 result
**CI success** run `35558185916` on `e2d1adc`.

## I — gunnchAI final CI
`GUNNCHAI_REQUIRED_CI_GREEN=true` on `e2d1adcb5847cf00282fb7fa64970254b14e344e`.

## J — gunnchAI candidate SHA
Pinned **`e2d1adcb5847cf00282fb7fa64970254b14e344e`**. Not `164bdb7`, not docs-only `d4a5c6d`, never `aa61e9`.

## K — live #21 head
Verified `8577e15a74edd07df7b3d159a195d8fe57d1c6b5`.

## L — WAIKE child branch/PR
https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/22 (draft) · branch `device-lab/pr21-real-gunnchai-ai-final-closure`

## M — fake-provider evidence reclassification
**DONE** → `WAIKE_AI_FIXTURE_SURFACE_PASS=true`. Product AI surface gates cleared pending REAL.

## N — real WAIKE→gunnchAI→Nearby Edge execution
**PASS** — `WAIKE_ALLOW_FAKE_AI=0`, pin `e2d1adcb5847cf00282fb7fa64970254b14e344e`. Hub `provider_id=nearby-edge` execute provenance `compute_host=mac_nearby_edge`, `on_device_local=false`, transport `ADB_REVERSE`, model `smollm2-135m-instruct-q4_k_m`. Nearby Mac is not on-device inference.

## O — benign tutoring result
API **PASS** (provenance above). Pixel CDP UI **PASS** (logged in, result length 619, no error).

## P — assessment guardrail
**PASS** — answer-key request refused `AI_INTEGRITY_REFUSED`.

## Q — fallback/unavailable result
**PASS** — live provider cleared; Hub returned `503 AI_PROVIDER_UNAVAILABLE` (honest, not a fake answer).

## R — lifecycle result
**PASS** — Home then Chrome resume; learner session still signed in (`hasLogout=true`).

## S — provenance truth
Nearby Mac ≠ on-device = true. Hub→NearbyEdge execute provenance = true.

## T — serial/evidence redaction audit
**PASS** — device alias `PIXEL_USB_DEVICE_1`. New journey/CDP artifacts contain no raw serial.

## U — Gate C
Exact-head CI on this child tip: **not yet green** (awaiting the push that records this proof).

## V — Gate D
Exact-head CI on this child tip: **not yet green**.

## W — device-lab workflows
aarch64 Linux + glibc236 + Windows Pilot 0: **awaiting** exact-head runs on the proof tip.

## X — final completion gate
`WAIKE_FULL_PLATFORM_COMPLETION_CANDIDATE_PASS=false`. REAL Nearby Edge route is earned and Agent A required CI is green on `e2d1adc`, but completion stays false until exact-head WAIKE CI is green on this tip. Human gates + MERGE_AUTHORIZED remain false.

## Y — draft PR URLs
- Parent #21: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/21
- This child #22: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/22
- gunnchAI #54: https://github.com/gunnchOS3k/gunnchAI3k/pull/54
- Agent A child #55: https://github.com/gunnchOS3k/gunnchAI3k/pull/55

## Z — remaining human blockers
1. Exact-head WAIKE CI green (Gate C/D, device-lab, Windows Pilot) on the proof tip.
2. Owner usability + disabled-user accessibility validation.
3. Owner merge authorization — **DO NOT MERGE** #20 / #21 / #22 / #54 / #55.

## Owner review checklist — unanswered
```text
[ ] Learner can use the platform end-to-end
[ ] Instructor can use their real role end-to-end
[ ] Grader / Guardian / Site Admin usable
[ ] Disabled-user accessibility human validation
[ ] Authorize merge (explicit)
```
