# WAIKE-PIXEL-1 A–Z report

## A. Accepted main SHA
`747e64e6386c10ef8c0f72c50eb5557035e5c9b9`

## B. Branch
`device-lab/pixel6a-full-waike-pilot` (from accepted main)

## C. Pixel baseline
See `artifacts/pixel6a_waike/DEVICE_BASELINE.json` — Pixel 6a, Android 17 / SDK 37, 1080x2400 @ 420dpi. Captured while ADB status was `device`.

**Current ADB:** `unauthorized` after later `adb kill-server`. Owner must re-accept USB debugging — see `OWNER_ADB_REAUTH.md`.

## D. Mac / Hub baseline
Pilot Hub on `127.0.0.1:8000` with `WAIKE_PIXEL_PILOT=true`, production password auth, fixture headers off. Vite client on `127.0.0.1:1420` with `VITE_HUB_URL` + `VITE_PIXEL_PILOT`.

## E. 18-track runtime inventory
`FULL_18_TRACK_RUNTIME_INVENTORY.json` — `all_18_loaded=true`, 18/18 IDs.

## F. Role manifest
`ROLE_TEST_MANIFEST.json` — learner/instructor/grader/guardian/site_admin (+ beta isolation users). Passwords only in gitignored `.pixel-pilot/credentials.json`.

## G. PWA / mobile-web
Manifest + SW shell cache; `runtimeAdapter` TAURI_DESKTOP / WEB_MOBILE; touch CSS; pilot banner; no mockHub in pixel pilot mode.

## H. Pixel↔Hub transport
ADB reverse `8000`/`1420` earned while authorized (`PIXEL_TO_REAL_HUB_CONNECTIVITY_PASS=true`). Re-reverse after re-auth.

## I–M. Role journeys (password API against real Hub)
Learner 18-track visibility, instructor, grader, guardian, site_admin — **pass** (API/password; physical UI remount blocked by unauthorized).

## N. Session isolation
**pass** (logout revokes token; sequential role logins).

## O. Cross-site isolation
**pass** (alpha admin cannot list beta users; alpha instructor denied beta roster).

## P. Offline / restart / reconnect
**false** — not earned; web IndexedDB offline explicitly unclaimed.

## Q. AI surfaces
**false** — not fully exercised on Pixel in this run.

## R. Accessibility mechanics
**false** — uiautomator dump blocked while unauthorized; remount required.

## S. Stability
**false** — full 30-minute soak not claimed (short sample only).

## T. Defects
None filed under `defects/` for Mac-side failures; physical remount gap documented in `OWNER_ADB_REAUTH.md`.

## U. Fixes
Exact-origin CORS (`cors_origins.py`); full curriculum seed; pilot users; mobile/PWA client; oracle + `make pixel-waike-full-pilot`.

## V. Regressions
`test_cors_origins.py`, `test_pixel_curriculum_seed.py`, `runtimeAdapter.test.ts`.

## W. Acceptance matrix
`PIXEL_FULL_ACCEPTANCE_MATRIX.csv`

## X. Native Android
Phase B — all native gates **false**.

## Y. Gate tokens
See `GATE_TOKENS.json`. Aggregate `WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS=false` (honest — physical remount + offline/soak/a11y outstanding).

## Z. DRAFT PR + next action
DRAFT PR: https://github.com/gunnchOS3k/gunnchos-waike-learning-platform/pull/19

`NEXT_WAIKE_ACTION=OWNER_REAUTH_USB_DEBUGGING_THEN_RERUN_make_pixel-waike-full-pilot`

Do not merge until aggregate gate is true after physical remount.
