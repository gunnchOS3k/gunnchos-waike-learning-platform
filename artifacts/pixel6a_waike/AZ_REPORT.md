# WAIKE-PIXEL-1 A–Z report

## A. Accepted main SHA
`747e64e6386c10ef8c0f72c50eb5557035e5c9b9`

## B. Branch / final SHA
Branch: `device-lab/pixel6a-full-waike-pilot`  
`06d90c166949a77b7c25ecbbbe924fc6b8ae3c13`

## C. Pixel baseline
`/Users/gunnchos/Downloads/gunnchos-7gc-research-product-spine/repos/gunnchos-waike-learning-platform/artifacts/pixel6a_waike/DEVICE_BASELINE.json`

- Serial `PIXEL_USB_DEVICE_1`, Google Pixel 6a (`bluejay`)
- Android 17 / SDK 37, 1080×2400 @ 420dpi
- Captured while ADB status was `device` (2026-09-18T23:00:32Z)
- **Current ADB:** `offline` (flaky USB). Owner must re-approve USB debugging — see `OWNER_ADB_REAUTH.md` and `defects/DEFECT-0001/`.

## D. Mac / Hub baseline
`artifacts/pixel6a_waike/MAC_HUB_BASELINE.json`

- Hub: `127.0.0.1:8000` (`WAIKE_PIXEL_PILOT=true`, production password auth, fixture headers off)
- Client: `127.0.0.1:1420`
- CORS: exact origins only (no `*`)
- DB: gitignored `.pixel-pilot/hub.sqlite3`

## E. 18-track runtime inventory
`artifacts/pixel6a_waike/FULL_18_TRACK_RUNTIME_INVENTORY.json` — `all_18_loaded=true`, exact 18 registry IDs.

Gate: `PIXEL_PILOT_ALL_18_TRACKS_LOADED=true`

## F. Role manifest
`artifacts/pixel6a_waike/ROLE_TEST_MANIFEST.json` — learner / instructor / grader / guardian / site_admin (+ beta isolation + unlinked guardian). Passwords only in gitignored `.pixel-pilot/credentials.json` (`password_present=true`, no password values in git).

Gate: `PIXEL_PILOT_ALL_ROLES_SEEDED=true`

## G. PWA / mobile-web
Manifest + shell SW (no `/api/` cache); `runtimeAdapter` `TAURI_DESKTOP` | `WEB_MOBILE`; touch CSS; pilot role banner; `VITE_PIXEL_PILOT` refuses silent mockHub.

Gates: `WAIKE_PIXEL_WEB_CLIENT_PASS=true`, `WAIKE_PIXEL_PWA_INSTALL_PASS=true`

## H. Pixel↔Hub transport
Preferred ADB reverse `tcp:8000` / `tcp:1420`. **Not currently earned** — device offline (`PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS=false`). Brief authorized windows earlier proved reverse listing possible.

## I–M. Role journeys
Mac password-API against real Hub: learner 18/18 tracks, instructor/grader/guardian/site_admin smoke, documented in `ROLE_JOURNEY_EVIDENCE.json` (`evidence_mode=mac_api_password_auth`, `MAC_API_ROLE_JOURNEYS_PROVEN=true`).

**PIXEL_* journey gates = false** until authorized Pixel + reverse (`PHYSICAL_UI_ROLE_JOURNEYS_PROVEN=false`). No fabricated physical UI success.

## N. Role / session isolation
Mac API: logout revokes token across sequential role logins (`mac_api_session_isolation`). `PIXEL_ROLE_SESSION_ISOLATION_PASS=false` pending physical eligibility.

## O. Cross-site isolation
Mac API: alpha admin does not list beta users; alpha instructor denied beta roster. `PIXEL_CROSS_SITE_ISOLATION_PASS=false` pending physical eligibility.

## P. Offline / restart / reconnect
`PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS=false` — not earned (ADB offline; IndexedDB path unclaimed).

## Q. AI surfaces
`PIXEL_WAIKE_AI_SURFACE_PASS=false` — honest fail; no fake provider; KIRBY not blocking.

## R. Accessibility
`PIXEL_ACCESSIBILITY_MECHANICS_PASS=false`. `HUMAN_DISABLED_USER_ACCESSIBILITY_VALIDATION=false`. Partial dumps under `artifacts/pixel6a_waike/accessibility/` from earlier authorized window.

## S. Performance / stability
Budgets defined in `PERFORMANCE_BUDGETS.json`. `PIXEL_WAIKE_STABILITY_PASS=false` (no 30-min soak).

## T. Defects
`artifacts/pixel6a_waike/defects/DEFECT-0001/` — `ADB_DEVICE_OFFLINE` (open).

## U. Fixes this wave
- Aligned `create_test_users.seed_pilot_users` with `pixel-*` keys + IdentityService
- Learner visibility via `/api/v1/learner/home` (18 exact tracks)
- Simplified Hub bootstrap (no wipe/race on fixture assignment seed)
- PIXEL_* journey gates require physical eligibility (no Mac-API-only greenwash)
- Tests under `tests/pixel_pilot/` (6 passed)

## V. Regressions added
- `tests/pixel_pilot/*` (curriculum seed, CORS, create_test_users, oracle)
- `apps/client` resolveHub + runtimeAdapter vitest (17 passed)

## W. Acceptance matrix
`artifacts/pixel6a_waike/PIXEL_FULL_ACCEPTANCE_MATRIX.csv`

## X. Native Android Phase B
`NATIVE_ANDROID_PHASE_B.json` — **DEFER**; all native gates false. PWA remains primary.

## Y. Gate tokens
`artifacts/pixel6a_waike/GATE_TOKENS.json`

| Token | Value |
|-------|-------|
| PIXEL6A_WAIKE_DEVICE_CONNECTED | false |
| PIXEL_PILOT_ALL_18_TRACKS_LOADED | true |
| PIXEL_PILOT_ALL_ROLES_SEEDED | true |
| WAIKE_PIXEL_WEB_CLIENT_PASS | true |
| PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS | false |
| WAIKE_PIXEL_PWA_INSTALL_PASS | true |
| PIXEL_LEARNER_18_TRACK_VISIBILITY_PASS | false |
| PIXEL_INSTRUCTOR_JOURNEY_PASS | false |
| PIXEL_GRADER_JOURNEY_PASS | false |
| PIXEL_GUARDIAN_JOURNEY_PASS | false |
| PIXEL_SITE_ADMIN_JOURNEY_PASS | false |
| PIXEL_ROLE_SESSION_ISOLATION_PASS | false |
| PIXEL_CROSS_SITE_ISOLATION_PASS | false |
| PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS | false |
| PIXEL_ACCESSIBILITY_MECHANICS_PASS | false |
| PIXEL_WAIKE_STABILITY_PASS | false |
| PIXEL_WAIKE_AI_SURFACE_PASS | false |
| WAIKE_ANDROID_NATIVE_* | false |
| HUMAN_DISABLED_USER_ACCESSIBILITY_VALIDATION | false |
| WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS | false |

## Z. DRAFT PR
https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/19 (DRAFT, do not merge)

### Next action
`NEXT_WAIKE_ACTION=OWNER_REAUTH_USB_DEBUGGING_THEN_RERUN_make_pixel-waike-full-pilot`

Preferred when fully green:
`NEXT_WAIKE_ACTION=FREEZE_PIXEL6A_FULL_CONTENT_ALL_ROLE_PILOT_BUILD_AND_BEGIN_OWNER_HUMAN_USABILITY_PASS`
