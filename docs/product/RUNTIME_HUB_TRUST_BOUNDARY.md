# Runtime Hub trust boundary

## Risk closed (PR #12 harden)

Launch-context `hub_url` must **not** be the sole authority that turns an arbitrary endpoint into the HTTP Hub base used for login passwords and bearer tokens.

## Sources of Hub base URL

| Source | Authority | Notes |
|--------|-----------|--------|
| Compile-time `VITE_HUB_URL` | Trusted build/config | Highest precedence; school image can bake HTTPS Hub; no mock |
| Runtime `context.hub_url` (Device OS launch IPC) | **Request only** | Must be authorized by `HubEndpointPolicy v1` at the Rust trust boundary before use |
| `HubEndpointPolicy v1` file / env | Trusted deployment policy | Authorizes exactly one normalized Hub base; provisioned by managed deploy / owner bundle / enrollment / Device Lab fixture |
| `VITE_WAIKE_MOCK_HUB` / `MODE=test` | Explicit test mock | Never used as fallback for untrusted runtime endpoints |

## Is launch context authenticated?

No. Device OS IPC launch context (`gunnchos.learning_os.ipc.v1`) is a local file-drop protocol with allowlisted keys. It is **not** a signed enrollment assertion and must not redirect credentials by itself.

## Credential paths (fail closed)

1. **Login** — `POST {base}/api/v1/auth/login` with username/password/`site_id` via `createHttpHubClient` only after `resolveHubClient` returns `status: "http"`.
2. **Bearer** — `Authorization: Bearer …` on subsequent Hub API calls from the same client.

Untrusted / unauthorized runtime Hub:

- `resolveHubClient` → `unavailable` (no client)
- no network request carrying credentials or tokens
- **no** `mockHub` fallback

## Existing trust machinery (audit)

| Mechanism | Role | Suitable for Hub URL authority? |
|-----------|------|----------------------------------|
| Learner pack verify-before-trust (`pack.rs`, signed manifests) | Content trust | No — different artifact class |
| Compatibility manifest | Pack/platform compatibility | No |
| Device OS launch allowlist + secret key rejection | IPC hygiene | Partial — accepts `hub_url` key but must not sole-authorize endpoint |
| **HubEndpointPolicy v1 (this PR)** | Deployment Hub endpoint authorization | **Yes** — smallest versioned policy for Hub base |

No pre-existing managed Hub trusted-origin / enrollment Hub binding was present; HubEndpointPolicy v1 is the additive authority (not a parallel pack-signing fork).

## Resolution precedence

1. Trusted configured/compile-time Hub (`VITE_HUB_URL`) — structurally normalized
2. Trusted runtime Hub — launch `hub_url` only after native `HubEndpointPolicy` authorization (`runtimeHubPolicyAuthorized`)
3. Explicit development/test mock under existing rules (`MODE=test` or `VITE_WAIKE_MOCK_HUB=true`)
4. Otherwise fail closed (`School Hub not configured / unavailable`)

## Transport rules

- Remote / production Hub: **HTTPS** (`require_https: true`, `allow_insecure_local: false`)
- Plain HTTP only when policy sets `allow_insecure_local: true` and authorizes the exact base (Device Lab example: `http://10.0.2.100:8787` or fixture `http://10.0.2.2:8787`)
- That Device Lab address is **not** hard-coded as production Hub

## Webview CSP connect-src (defense-in-depth)

Static `tauri.conf.json` uses fail-closed:

`connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost`

At process start (before webview), `hub_connect_csp` appends **exact** origins from:

1. Provisioned HubEndpointPolicy `authorized_hub_base_url` (HTTP→`ws:`, HTTPS→`wss:` pair)
2. Compile-time `VITE_HUB_URL` when baked into the image

**Forbidden:** scheme-wide `http:` / `https:` / `ws:` / `wss:` (would allow arbitrary hosts and undermine this policy).

Untrusted hubs: policy rejects credential path **and** CSP omits their origin.

## Policy load order (trusted provision)

1. `WAIKE_HUB_ENDPOINT_POLICY_JSON`
2. `WAIKE_HUB_ENDPOINT_POLICY_PATH`
3. `{data_dir}/com.gunnchos.waike.learning/hub_endpoint_policy.v1.json`

Schema: `contracts/schemas/hub_endpoint_policy.v1.json`  
Device Lab fixture: `contracts/fixtures/device_lab_hub_endpoint_policy.v1.json`

## Native URL rules (Rust)

`hub_endpoint_policy::parse_hub_base_url` uses the `url` crate (not JS string-prefix):

- scheme exactly `http` or `https`
- non-empty host; valid port; no userinfo; no fragment; no query
- no NUL/control; no backslash confusion
- reject `file:`, `javascript:`, unsupported schemes
- canonicalize trailing slash / host case; preserve non-default port and non-root path

Authorization requires normalized equality to `authorized_hub_base_url` plus transport flags / optional `expires_at`.

## Device Lab post-merge integration contract (prefer not changing Device OS #134 here)

After owner merge of this WAIKE PR and glibc236 artifact re-freeze:

1. Provision `HubEndpointPolicy v1` into the guest (env `WAIKE_HUB_ENDPOINT_POLICY_PATH` / `WAIKE_HUB_ENDPOINT_POLICY_JSON` or managed data-dir file) authorizing **exactly** the Device Lab Hub base used in launch context (e.g. `http://10.0.2.100:8787` or `http://10.0.2.2:8787`) with `allow_insecure_local: true`, `require_https: false`, provenance `device_lab_fixture` (or later `managed_policy`). Runtime CSP connect-src follows that same exact origin.
2. Continue passing launch-context `hub_url` matching that authorized base.
3. Keep mockHub disabled (`VITE_WAIKE_MOCK_HUB` unset/false).
4. Re-earn `WAIKE_REAL_RUNTIME_DEVICE_LAB_PASS` / GUI+Hub journey on the new accepted-main pin.

Future school/community deploys authorize their HTTPS Hub by provisioning policy — **no per-site WAIKE rebuild required** (CSP updates at process start from policy).

## Claim boundary

`WAIKE_REAL_RUNTIME_DEVICE_LAB_PASS` remains false until owner merge + refreeze + re-earn. Cursor merges nothing.
