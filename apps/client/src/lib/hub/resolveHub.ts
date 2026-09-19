import type { AuthSession, HubActor, HubClient } from "./client";
import { createHttpHubClient } from "./client";
import { createMockHubClient } from "./mockHub";

export type HubResolution =
  | { status: "http"; client: HubClient; baseUrl: string }
  | { status: "mock"; client: HubClient }
  | { status: "unavailable"; client: null; reason: string };

export type HubEnv = {
  MODE?: string;
  VITE_HUB_URL?: string;
  VITE_WAIKE_MOCK_HUB?: string;
  /** Pixel physical pilot — production-shaped; never allow silent mockHub fallback. */
  VITE_PIXEL_PILOT?: string;
  /**
   * Runtime Hub base URL from Device OS launch context (`hub_url`).
   * Only honored when `runtimeHubPolicyAuthorized` is true (native policy already passed).
   * Compile-time `VITE_HUB_URL` still wins when set. Never enables mock by itself.
   */
  runtimeHubUrl?: string;
  /**
   * Set only after Rust/native HubEndpointPolicy authorization.
   * Launch context alone must not set this from untrusted JS.
   */
  runtimeHubPolicyAuthorized?: boolean;
};

/**
 * Defense-in-depth structural normalize for Hub bases.
 * Native Rust `parse_hub_base_url` remains the security boundary for launch-context URLs.
 */
export function structuralNormalizeHubBase(
  raw: string,
): { ok: true; base: string } | { ok: false; reason: string } {
  if (!raw) return { ok: false, reason: "hub_url_empty" };
  if (/[\u0000-\u001f]/.test(raw)) return { ok: false, reason: "hub_url_control_char" };
  if (raw.includes("\\")) return { ok: false, reason: "hub_url_backslash" };
  if (/\s/.test(raw)) return { ok: false, reason: "hub_url_whitespace" };
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return { ok: false, reason: "hub_url_parse_failed" };
  }
  if (u.protocol === "file:") return { ok: false, reason: "hub_url_scheme_file" };
  if (u.protocol === "javascript:") return { ok: false, reason: "hub_url_scheme_javascript" };
  if (u.protocol !== "https:" && u.protocol !== "http:") {
    return { ok: false, reason: `hub_url_scheme_unsupported:${u.protocol.replace(/:$/, "")}` };
  }
  if (u.username || u.password) return { ok: false, reason: "hub_url_userinfo" };
  if (u.hash) return { ok: false, reason: "hub_url_fragment" };
  if (u.search) return { ok: false, reason: "hub_url_query" };
  if (!u.hostname) return { ok: false, reason: "hub_url_empty_host" };

  const host = u.hostname.toLowerCase();
  let out = `${u.protocol}//${host}`;
  if (u.port) out += `:${u.port}`;
  let path = u.pathname || "";
  if (path === "/" || path === "") {
    // origin only
  } else {
    path = path.replace(/\/+$/, "");
    if (path) out += path;
  }
  return { ok: true, base: out };
}

/**
 * Fail-closed hub resolution: never silently mock in production/native.
 *
 * Precedence:
 * 1. trusted configured/compile-time Hub (`VITE_HUB_URL`)
 * 2. trusted runtime Hub authorized by HubEndpointPolicy (`runtimeHubUrl` + flag)
 * 3. explicit development mock only under existing dev rules
 * 4. otherwise fail closed (unavailable) — never mockHub for untrusted endpoints
 */
export function resolveHubClient(
  getToken: () => string | null,
  onAuthFailure?: (detail: string) => void,
  actor?: HubActor,
  env: HubEnv = import.meta.env,
): HubResolution {
  const viteRaw = (env.VITE_HUB_URL || "").trim();
  if (viteRaw) {
    const checked = structuralNormalizeHubBase(viteRaw.replace(/\/$/, ""));
    if (!checked.ok) {
      return {
        status: "unavailable",
        client: null,
        reason: `School Hub misconfigured (${checked.reason})`,
      };
    }
    return {
      status: "http",
      client: createHttpHubClient(checked.base, getToken, onAuthFailure, undefined),
      baseUrl: checked.base,
    };
  }

  const runtimeRaw = (env.runtimeHubUrl || "").trim();
  if (runtimeRaw) {
    if (!env.runtimeHubPolicyAuthorized) {
      return {
        status: "unavailable",
        client: null,
        reason: "Hub endpoint not authorized by trusted policy",
      };
    }
    const checked = structuralNormalizeHubBase(runtimeRaw.replace(/\/$/, ""));
    if (!checked.ok) {
      return {
        status: "unavailable",
        client: null,
        reason: `Hub endpoint rejected (${checked.reason})`,
      };
    }
    return {
      status: "http",
      client: createHttpHubClient(checked.base, getToken, onAuthFailure, undefined),
      baseUrl: checked.base,
    };
  }

  const pixelPilot =
    String(env.VITE_PIXEL_PILOT || "").toLowerCase() === "true" ||
    String(env.VITE_PIXEL_PILOT || "") === "1";
  // Production-shaped Pixel pilot: refuse mock even if VITE_WAIKE_MOCK_HUB is set.
  const allowMock =
    !pixelPilot &&
    (env.MODE === "test" || String(env.VITE_WAIKE_MOCK_HUB || "").toLowerCase() === "true");
  if (allowMock) {
    const mockActor = actor ?? { actorId: "learner-a", role: "learner" as const };
    return { status: "mock", client: createMockHubClient(mockActor) };
  }
  if (pixelPilot) {
    return {
      status: "unavailable",
      client: null,
      reason: "Pixel pilot requires VITE_HUB_URL (no mockHub fallback)",
    };
  }
  return {
    status: "unavailable",
    client: null,
    reason: "School Hub not configured / unavailable",
  };
}

export type { AuthSession };
