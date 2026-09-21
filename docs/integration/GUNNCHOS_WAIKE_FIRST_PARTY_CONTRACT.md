# gunnchOS ↔ WAIKE First-Party Integration Contract

**Owner surface:** WAIKE Learning Platform (`gunnchOS3k/gunnchos-waike-learning-platform`)  
**Counterpart (read-only in this pass):** gunnchOS Device OS (`gunnchOS3k/gunnchos-device-os`)  
**Policy:** WAIKE defines and verifies what it exposes. This document does **not** modify Device OS.

## 1. Delivery model (truth)

| Channel | Role | Status on accepted main |
|---------|------|-------------------------|
| Platform Tauri bundle `com.gunnchos.waike.learning` | System of record LMS client | Primary standalone desktop delivery |
| Pixel / mobile web PWA (`apps/client` + Hub) | Development + physical pilot | Primary Pixel evidence path |
| Device OS SDK `gunnchos.waike_learning` + `apps/waike_learning` HTML seed | Thin launcher / discovery companion | **FULL_VIA_ADAPTER** — not a second LMS SoR |
| Native Android WAIKE APK | Optional Phase B | Deferred (`WAIKE_ANDROID_NATIVE_*` remain false unless separately earned) |

**Production first-party embedding on gunnchOS is `FULL_VIA_ADAPTER`:** Device OS launches/continues into the Platform client (Tauri or authorized web/PWA surface) via the integration contract below. Companion HTML/SDK is not the curriculum system of record.

## 2. Stable identifiers

| Field | Value |
|-------|-------|
| Platform registry id | `waike_learning_os` |
| Compatibility alias | `waike_offline` |
| SDK app id | `gunnchos.waike_learning` |
| Runtime id | `waike` |
| Tauri bundle id | `com.gunnchos.waike.learning` |
| Machine contract | `contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json` |
| Device OS pin snapshot | `contracts/deviceos/CONTRACT_SNAPSHOT.json` (Gate C baseline after Device OS PR #132) |

## 3. Launch / deep-link

- **Scheme:** `waike://`
- **Kinds:** `learn` · `section` · `quiz` · `assignment` · `sync` · `device`
- Platform maps deep-link kinds to client modes via `modeForDeviceOsDeepLink` (never bypasses auth).
- Launch context may supply `hub_url` only after **native** HubEndpointPolicy authorization (`runtimeHubPolicyAuthorized`).

## 4. Auth / session

- Production-shaped Hub password auth (`/api/v1/auth/login`, Bearer token).
- Fixture-auth headers are **off** for Pixel pilot (`WAIKE_PIXEL_PILOT` / `VITE_PIXEL_PILOT`).
- Logout revokes tokens; subsequent `/api/v1/auth/me` must 401/403.
- Role precedence: `site_admin` > `instructor` > `grader` > `guardian` > `learner`.

## 5. Role / continue-learning / offline state WAIKE exposes

| Concern | WAIKE exposure |
|---------|----------------|
| Role state | Session user `roles[]` + primary-role UI modes (`home`, `instruct`, `gradebook`, `guardian`, `admin`, …) |
| Current track/course | Learner home sections + package `module_id`; curriculum inventory `/api/v1/pilot/curriculum-inventory` (pilot) |
| Continue-learning | Offline sync coordinator + leases; Device OS continuity coordinator owns OS-level checkpoints |
| Offline/sync | Client IndexedDB queue + Hub sync APIs; SyncStatusBanner UX |
| Return-to-gunnchOS | Deep-link / continuity handoff; Platform does not own Device OS shell chrome |
| Error/unavailable | Fail-closed Hub resolution (`unavailable` status); no silent mock in Pixel/production |
| Search/index metadata | Not a required first-party search SoR in this contract revision — expose only if Device OS requests a later revision |

## 6. Permissions mapping (WAIKE roles → Device OS roles)

See `contracts/deviceos/WAIKE_LEARNING_OS_INTEGRATION_CONTRACT.json` → `permissions_mapping` for learner / instructor / grader / guardian / site_admin.

## 7. AI / gunnchAI boundary

- WAIKE AI panels call Hub AI routes under current policy (context isolation, prompt-injection, grade-safety tests in Gate B).
- Fail honestly when AI unavailable; no silent remote cloud provider brand requirement.
- Compatibility verified via `scripts/verify_gunnchai_contract.py` / Gate B AI suite against local `GUNNCHAI_ROOT`.

## 8. Claim boundary

> Platform consumes Device OS launcher / permissions / continuity / updater modules when `DEVICE_OS_ROOT` is set. Seed HTML is not LMS SoR. Digital integration only unless a separate physical Device OS + Platform handoff is evidenced.

## 9. Verification expectations (WAIKE side)

1. Gate C Device OS acceptance artifacts remain green against pinned Device OS main.
2. Pixel / desktop clients honor HubEndpointPolicy and production auth.
3. First-party adapter path preserves all five roles and 18-track inventory without requiring a separate native Android LMS.
4. Native Android Phase B gates stay false until a real APK build/install/smoke is earned — not relabeled for marketing.

## 10. Non-claims

This contract does **not** claim school deployment, K-12 approval, accessibility certification, or district production acceptance.
