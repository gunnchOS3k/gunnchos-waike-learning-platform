# DRAFT: CSP connect-src for Device OS runtime Hub

## Problem
Accepted-main `tauri.conf.json` sets `default-src 'self'` without `connect-src`.
Under CSP3, `fetch()` to a Device OS policy-authorized Hub (`http://10.0.2.100:8787`)
is blocked. Device Lab 17G.5D proves:

- Trusted launch ACK with `hub_url` in context
- Guest Hub reachability PASS (restrict=on + hub-only guestfwd)
- Authentic GUI login drive completes (`agent_abs_click_enter_submit`)
- WebKit opens TCP to authorized Hub
- Hub access log remains healthz-only (no `/api/v1/auth/login`)

## Fix
Add `connect-src 'self' http: https: ws: wss:` so runtime Hub bases authorized by
native HubEndpointPolicy can be reached. Native policy remains the security boundary
for which Hub URL is accepted into launch context.

## Device Lab tokens
Keep `WAIKE_REAL_RUNTIME=false` until a rebuilt artifact is re-pinned on Device OS.
Base SHA: 232fc8dc3aa10d3dd644ef48d1d8c63da50d4d3c
