# CSP connect-src for Device OS runtime Hub

## Problem
Accepted-main `tauri.conf.json` set `default-src 'self'` without an explicit
`connect-src`. Under CSP3, `fetch()` to a Device OS policy-authorized Hub
(e.g. `http://10.0.2.100:8787`) is blocked. Device Lab 17G.5F/17G.5D proves:

- Trusted launch ACK with `hub_url` in context
- Guest Hub reachability PASS (restrict=on + hub-only guestfwd)
- Authentic GUI login drive completes
- WebKit opens TCP to authorized Hub
- Hub access log remains healthz-only (no `/api/v1/auth/login`)

An earlier DRAFT patch used `connect-src 'self' http: https: ws: wss:`. That is
**too broad**: it would allow webview `fetch` to arbitrary HTTP(S) hosts and
undermine the HubEndpointPolicy v1 trust boundary from PR #12.

## Fix (policy-aligned)
1. **Static CSP (fail closed):**  
   `connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost`  
   (IPC sources are required once `connect-src` is explicit; they replace the
   previous implicit `default-src 'self'` coverage for Tauri IPC.)
2. **Runtime injection (before webview start):**  
   `hub_connect_csp` loads HubEndpointPolicy v1 and appends **exact** authorized
   Hub origin(s) plus matching `ws:`/`wss:` origins for the same host:port.  
   Optional compile-time `VITE_HUB_URL` is additive (school image bake).
3. **Never** emit scheme-wide `http:` / `https:` / `ws:` / `wss:` tokens.

Native HubEndpointPolicy remains the credential/token authorization boundary.
CSP is defense-in-depth so unauthorized origins cannot receive webview connect
traffic even if JS misbehaves.

## Trust model
| Layer | Role |
|-------|------|
| HubEndpointPolicy v1 | Authorizes which Hub base may enter launch context / receive credentials |
| Runtime CSP `connect-src` | Allows webview `fetch`/WebSocket **only** to `'self'`, Tauri IPC, and policy (or bake-time) Hub origin(s) |
| `resolveHubClient` | Fail-closed; no mockHub for untrusted runtime endpoints |

## Device Lab local exception
Plain HTTP is allowed in CSP **only** when HubEndpointPolicy authorizes that
exact base with `allow_insecure_local: true` (example:
`http://10.0.2.100:8787`). Neighbor addresses (e.g. `10.0.2.2`, `127.0.0.1`)
are not implied. Production remote Hub remains HTTPS.

## Device Lab tokens / post-merge contract
- Keep **`WAIKE_REAL_RUNTIME=false`** until owner merge → glibc236 rebuild →
  Device OS accepted-main re-freeze → GUI+Hub journey re-earn.
- Cursor merges nothing.
- Base SHA at PR open: `232fc8dc3aa10d3dd644ef48d1d8c63da50d4d3c` (PR #12).
- After merge: provision policy authorizing the **exact** Device Lab Hub base
  used in launch context; do not modify Device OS #134 in this WAIKE PR.
