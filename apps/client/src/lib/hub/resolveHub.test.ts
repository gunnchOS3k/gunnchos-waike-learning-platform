import { describe, expect, it, vi, afterEach } from "vitest";
import { createHttpHubClient } from "./client";
import { resolveHubClient } from "./resolveHub";
import { resetMockHubStore } from "./mockHub";

afterEach(() => {
  resetMockHubStore();
  vi.unstubAllGlobals();
});

const getToken = () => null;
const actor = { actorId: "learner-a", role: "learner" as const };

describe("resolveHubClient fail-closed", () => {
  it("uses deterministic mock in test mode without hub URL", () => {
    const r = resolveHubClient(getToken, undefined, actor, { MODE: "test" });
    expect(r.status).toBe("mock");
    expect(r.client).not.toBeNull();
  });

  it("uses mock when VITE_WAIKE_MOCK_HUB=true outside test", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      VITE_WAIKE_MOCK_HUB: "true",
    });
    expect(r.status).toBe("mock");
  });

  it("does not create mock assessment state in production without hub config", () => {
    const r = resolveHubClient(getToken, undefined, actor, { MODE: "production" });
    expect(r.status).toBe("unavailable");
    expect(r.client).toBeNull();
    if (r.status === "unavailable") {
      expect(r.reason).toMatch(/School Hub not configured/i);
    }
  });

  it("does not create mock in native/development without hub or explicit mock flag", () => {
    const r = resolveHubClient(getToken, undefined, actor, { MODE: "development" });
    expect(r.status).toBe("unavailable");
    expect(r.client).toBeNull();
  });

  it("creates HTTP hub client when VITE_HUB_URL is configured", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      VITE_HUB_URL: "https://hub.example.edu/",
    });
    expect(r.status).toBe("http");
    if (r.status === "http") {
      expect(r.baseUrl).toBe("https://hub.example.edu");
      expect(r.client).not.toBeNull();
    }
  });
});

describe("createHttpHubClient", () => {
  it("sends bearer token when session present", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response(
          JSON.stringify([{ assignment_id: "digital_confidence_w01", title: "Mental model reflection" }]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const client = createHttpHubClient("http://127.0.0.1:8765", () => "tok_abc");
    const list = await client.listAssignments();
    expect(list[0]?.assignment_id).toBe("digital_confidence_w01");
    expect(calls[0]?.url).toBe("http://127.0.0.1:8765/api/v1/assignments");
    const headers = calls[0]?.init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok_abc");
  });

  it("posts grades without force_mastery_gap", async () => {
    let body: string | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        body = String(init?.body || "");
        return new Response(
          JSON.stringify({
            grade: { grade_id: "g1", points_earned: 10, points_possible: 20, returned: 1, revision: 1 },
            mastery: { mastered: 0, gap_notes: "gap" },
            remediation: { status: "assigned" },
            portfolio: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const client = createHttpHubClient("http://hub.local", () => "tok");
    await client.grade("sub1", {
      criterion_scores: [{ criterion_id: "crit_a", points: 2 }],
      feedback_body: "ok",
    });
    const parsed = JSON.parse(body || "{}");
    expect(parsed.return_to_learner).toBe(true);
    expect(parsed).not.toHaveProperty("force_mastery_gap");
  });
});
