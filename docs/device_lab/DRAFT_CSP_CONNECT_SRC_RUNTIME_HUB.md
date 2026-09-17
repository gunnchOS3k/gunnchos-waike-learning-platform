# CSP connect-src runtime apply (Device Lab / WebKitGTK)

## Problem (post-#14)
Accepted-main merge #14 (`95c7b847…`) added exact-origin Runtime Hub
`connect-src` via `Context::config_mut` before `.run`. Source contract PASS:

- no scheme-wide `http:` / `https:`
- policy appends exact origin (e.g. `http://10.0.2.100:8787`)

Device Lab 17G.5E still observed:

- Trusted launch ACK + HubEndpointPolicy authorized
- Guest Hub reachability PASS
- GUI login form driven
- Hub access log healthz-only (no `/api/v1/auth/login`)

`/proc/<pid>/net/tcp` “WebKit → hub” hits are **not** proof of client HTTP:
every process in the guest netns sees the same TCP table.

## Root cause (apply path)
1. Tauri applies CSP mainly as a custom-protocol **response header**.
2. WebKitGTK has historically been unreliable about honoring CSP headers on
   `tauri://` documents; Tauri’s own `set_csp` comment still mentions Linux HTML
   injection, but current Tauri 2.11 only sets the header + script/style nonces.
3. #14 had **no runtime evidence** that the effective WebView policy contained the
   authorized Hub origin (no stderr dump, no HTML meta).
4. Login fetch failures were silent in the GUI log scrape.

This is a **WAIKE product** apply/observability defect, not a Device OS
HubEndpointPolicy defect. Do not weaken HubEndpointPolicy. Do not add scheme-wide
tokens. Do not use mockHub.

## Fix
1. Apply CSP as `Csp::DirectiveMap` (avoid Policy-string round-trip).
2. Fold the already-authorized launch `hub_url` into connect-src (same process as ACK).
3. Assert launch hub origin is present in effective connect-src after apply.
4. Inject the same effective CSP as HTML `<meta http-equiv="Content-Security-Policy">`
   via an assets wrapper **before** first navigation.
5. Log `WAIKE_EFFECTIVE_CSP_CONNECT_SRC=…` / `WAIKE_EFFECTIVE_CSP=…` to stderr.
6. Frontend: `securitypolicyviolation` + login fetch start/error via `report_client_diag`.

## Tests
- Authorized origin appears in effective connect-src; unauthorized does not.
- `apply_hub_connect_csp_to_config_with_launch` mutates the config slot.
- HTML meta injection embeds authorized origin, not evil / scheme wildcards.

## Device Lab tokens / post-merge contract
- Keep **`WAIKE_REAL_RUNTIME=false`** / **`WAIKE_REAL_HUB_CLIENT_BIND_PASS=false`**
  until owner merge → glibc236 rebuild → accepted-main re-freeze → GUI+Hub re-earn.
- Cursor merges nothing.
