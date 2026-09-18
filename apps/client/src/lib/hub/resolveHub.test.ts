import { describe, expect, it, vi, afterEach } from "vitest";
import { createHttpHubClient } from "./client";
import { resolveHubClient, structuralNormalizeHubBase } from "./resolveHub";
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

  it("refuses mockHub when VITE_PIXEL_PILOT is set even if mock flag present", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      VITE_PIXEL_PILOT: "true",
      VITE_WAIKE_MOCK_HUB: "true",
    });
    expect(r.status).toBe("unavailable");
    expect(r.client).toBeNull();
    if (r.status === "unavailable") {
      expect(r.reason).toMatch(/Pixel pilot requires VITE_HUB_URL/i);
    }
  });

  it("creates HTTP hub client from policy-authorized Device OS runtimeHubUrl without enabling mock", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      runtimeHubUrl: "http://10.0.2.2:8787/",
      runtimeHubPolicyAuthorized: true,
    });
    expect(r.status).toBe("http");
    if (r.status === "http") {
      expect(r.baseUrl).toBe("http://10.0.2.2:8787");
      expect(r.client).not.toBeNull();
    }
  });

  it("prefers VITE_HUB_URL over runtimeHubUrl", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      VITE_HUB_URL: "https://hub.example.edu",
      runtimeHubUrl: "http://10.0.2.2:8787",
      runtimeHubPolicyAuthorized: true,
    });
    expect(r.status).toBe("http");
    if (r.status === "http") {
      expect(r.baseUrl).toBe("https://hub.example.edu");
    }
  });

  it("rejects unauthorized runtimeHubUrl without policy flag and does not mock", () => {
    const r = resolveHubClient(getToken, undefined, actor, {
      MODE: "production",
      runtimeHubUrl: "https://evil.example",
    });
    expect(r.status).toBe("unavailable");
    expect(r.client).toBeNull();
    if (r.status === "unavailable") {
      expect(r.reason).toMatch(/not authorized by trusted policy/i);
    }
  });

  it("request-spy: rejected runtime endpoint emits neither login credentials nor bearer token", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response("{}", { status: 200 });
      }),
    );

    const r = resolveHubClient(() => "secret-bearer-token", undefined, actor, {
      MODE: "production",
      runtimeHubUrl: "https://evil.example",
      // deliberately omit runtimeHubPolicyAuthorized
    });
    expect(r.status).toBe("unavailable");
    expect(r.client).toBeNull();

    // No client → login path cannot run; prove fetch was never touched.
    expect(calls).toHaveLength(0);

    // Even if a caller mistakenly builds a client from the raw evil URL, our
    // resolveHub path must not have done so. Double-check unauthorized resolve.
    const r2 = resolveHubClient(() => "secret-bearer-token", undefined, actor, {
      MODE: "production",
      runtimeHubUrl: "http://evil.example",
      runtimeHubPolicyAuthorized: false,
    });
    expect(r2.client).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it("request-spy: authorized runtime hub may send credentials only after trust", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response(
          JSON.stringify({
            token: "tok",
            expires_at: "2099-01-01T00:00:00Z",
            user: {
              user_id: "u1",
              username: "u1",
              display_name: "U",
              site_id: "device-lab",
              roles: ["learner"],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const r = resolveHubClient(() => null, undefined, actor, {
      MODE: "production",
      runtimeHubUrl: "http://10.0.2.2:8787",
      runtimeHubPolicyAuthorized: true,
    });
    expect(r.status).toBe("http");
    if (r.status === "http") {
      await r.client.login("learner", "pw", "device-lab");
    }
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe("http://10.0.2.2:8787/api/v1/auth/login");
    expect(String(calls[0]?.init?.body || "")).toContain("learner");
  });
});

describe("structuralNormalizeHubBase", () => {
  it("normalizes trailing slash and accepts https school hub", () => {
    const r = structuralNormalizeHubBase("https://hub.school.example/");
    expect(r).toEqual({ ok: true, base: "https://hub.school.example" });
  });

  it("rejects file javascript userinfo fragment path-like", () => {
    expect(structuralNormalizeHubBase("/etc/passwd").ok).toBe(false);
    expect(structuralNormalizeHubBase("file:///etc/passwd").ok).toBe(false);
    expect(structuralNormalizeHubBase("javascript:alert(1)").ok).toBe(false);
    expect(structuralNormalizeHubBase("https://user:password@hub.example").ok).toBe(false);
    expect(structuralNormalizeHubBase("https://hub.example/path#frag").ok).toBe(false);
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
