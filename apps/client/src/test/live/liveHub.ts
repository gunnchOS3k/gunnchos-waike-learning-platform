import type {
  LeaseResponse,
  MutationReceipt,
  PullResult,
  SyncTransport,
} from "../../lib/offline/syncCoordinator";

export const FIXTURE_PASSWORD = "WaikeTestPass1!";
export const SECTION = "sec_alpha_dc_w01";
export const SITE = "site-alpha";

export function hubUrl(): string {
  const url = process.env.WAIKE_LIVE_HUB_URL;
  if (!url) throw new Error("live hub not started");
  return url;
}

export class HttpError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status}:${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export interface LiveSession {
  token: string;
  userId: string;
  siteId: string;
  req<T>(path: string, init?: RequestInit): Promise<T>;
}

export async function login(username: string, siteId = SITE): Promise<LiveSession> {
  const base = hubUrl();
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password: FIXTURE_PASSWORD, site_id: siteId }),
  });
  if (!res.ok) throw new HttpError(res.status, await res.text());
  const body = (await res.json()) as { token: string; user: { user_id: string; site_id: string } };

  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${body.token}`,
        ...(init?.headers || {}),
      },
    });
    if (!r.ok) {
      const text = await r.text();
      let detail = text;
      try {
        detail = (JSON.parse(text) as { detail?: string }).detail || text;
      } catch {
        /* raw body */
      }
      throw new HttpError(r.status, String(detail));
    }
    if (r.status === 204) return undefined as T;
    return (await r.json()) as T;
  }

  return { token: body.token, userId: body.user.user_id, siteId: body.user.site_id, req };
}

/** Real HTTP transport; no mocking anywhere in the request path. */
export function liveTransport(session: LiveSession): SyncTransport {
  return {
    issueLease: (sectionId, deviceId, ttlHours = 72) =>
      session.req<LeaseResponse>("/api/v1/sync/leases", {
        method: "POST",
        body: JSON.stringify({ section_id: sectionId, device_id: deviceId, ttl_hours: ttlHours }),
      }),
    getLease: (leaseId) => session.req<LeaseResponse>(`/api/v1/sync/leases/${leaseId}`),
    applyMutation: (body) =>
      session.req<MutationReceipt>("/api/v1/sync/mutations", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    getReceipt: (id) => session.req<MutationReceipt>(`/api/v1/sync/receipts/${id}`),
    pullChanges: (sectionId, sinceRevision) =>
      session.req<PullResult>(
        `/api/v1/sync/pull?section_id=${encodeURIComponent(sectionId)}&since_revision=${sinceRevision}`,
      ),
  };
}

let counter = 0;
export function mutationId(prefix: string): string {
  counter += 1;
  return `mut_${prefix}_${Date.now().toString(36)}_${counter}`;
}
