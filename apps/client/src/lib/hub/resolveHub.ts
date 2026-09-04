import type { HubActor, HubClient } from "./client";
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
};

/** Fail-closed hub resolution: never silently mock in production/native. */
export function resolveHubClient(actor: HubActor, env: HubEnv = import.meta.env): HubResolution {
  const base = (env.VITE_HUB_URL || "").trim().replace(/\/$/, "");
  if (base) {
    return { status: "http", client: createHttpHubClient(base, actor), baseUrl: base };
  }
  const allowMock =
    env.MODE === "test" || String(env.VITE_WAIKE_MOCK_HUB || "").toLowerCase() === "true";
  if (allowMock) {
    return { status: "mock", client: createMockHubClient(actor) };
  }
  return {
    status: "unavailable",
    client: null,
    reason: "School Hub not configured / unavailable",
  };
}
