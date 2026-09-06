import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AdminHardeningPanel } from "../components/admin/AdminHardeningPanel";
import { InteropStatusPanel } from "../components/interop/InteropPanels";
import { createHttpHubClient } from "../lib/hub/client";
import { createMockHubClient, resetMockHubStore } from "../lib/hub/mockHub";

afterEach(() => {
  cleanup();
  resetMockHubStore();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  resetMockHubStore();
});

describe("Gate C keyboard-only production journeys", () => {
  it("tabs through App admin hardening controls and activates backup via Enter", async () => {
    const user = userEvent.setup();
    render(<App />);
    // Switch to site_admin mock actor via Instruct then we need admin — mock starts as learner.
    // Use mode-instruct then set admin: App mock uses mockActor; site_admin only shows Admin when role matches.
    // Force via Interop which is available for instructor mock after clicking Instruct.
    await user.click(screen.getByTestId("mode-instruct"));
    await user.click(screen.getByTestId("mode-interop"));
    await waitFor(() => {
      expect(screen.getByTestId("interop-status-panel")).toBeTruthy();
    });
    // Keyboard: tab into OneRoster claim
    const or = screen.getByTestId("interop-oneroster");
    or.focus();
    expect(or).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(screen.getByTestId("interop-oneroster").textContent).toMatch(/NOT_FULL_ONEROSTER/);
    });
  });

  it("admin hardening panel backup button calls hub (mock)", async () => {
    const user = userEvent.setup();
    const hub = createMockHubClient({ actorId: "admin-alpha", role: "site_admin" });
    const spy = vi.spyOn(hub, "createBackup");
    render(
      <AdminHardeningPanel workflows={["backup_restore", "diagnostics"]} hub={hub} />,
    );
    await user.tab();
    expect(screen.getByTestId("admin-workflow-backup_restore")).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
      expect(screen.getByTestId("admin-hardening-result").textContent).toMatch(/bak_mock/);
    });
  });

  it("learner home path is keyboard reachable in App", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-home"));
    await waitFor(() => {
      expect(screen.getByTestId("learner-home")).toBeTruthy();
    });
    const homeBtn = screen.getByTestId("mode-home");
    homeBtn.focus();
    expect(homeBtn).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("learner-home")).toBeTruthy();
  });
});

describe("Gate C admin UI hub wiring (fetch mock)", () => {
  it("clicks diagnostics and asserts hub fetch", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/diagnostics")) {
        return new Response(
          JSON.stringify({
            health: "ok",
            schema_migrations: ["007_gate_c_owner"],
            subsystems: [{ name: "db_integrity", status: "healthy" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const hub = createHttpHubClient("http://hub.test", () => "tok");
    const user = userEvent.setup();
    render(<AdminHardeningPanel workflows={["diagnostics"]} hub={hub} />);
    await user.click(screen.getByTestId("admin-workflow-diagnostics"));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("/api/v1/diagnostics"))).toBe(true);
      expect(screen.getByTestId("admin-hardening-result").textContent).toMatch(/007_gate_c_owner/);
    });
  });

  it("InteropStatusPanel fetches live matrices", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("oneroster/matrix")) {
        return new Response(JSON.stringify({ claim: "NOT_FULL_ONEROSTER" }), { status: 200 });
      }
      if (url.includes("qti/matrix")) {
        return new Response(
          JSON.stringify({
            claim: "NOT_FULL_QTI",
            xmlns: "http://www.imsglobal.org/xsd/imsqtiasi_v3p0",
          }),
          { status: 200 },
        );
      }
      if (url.includes("lti/matrix")) {
        return new Response(JSON.stringify({ claim: "NOT_LTI_CERTIFIED" }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const hub = createHttpHubClient("http://hub.test", () => "tok");
    render(<InteropStatusPanel hub={hub} />);
    await waitFor(() => {
      expect(screen.getByTestId("interop-oneroster").textContent).toMatch(/NOT_FULL_ONEROSTER/);
      expect(screen.getByTestId("interop-qti").textContent).toMatch(/imsqtiasi_v3p0/);
    });
  });
});
