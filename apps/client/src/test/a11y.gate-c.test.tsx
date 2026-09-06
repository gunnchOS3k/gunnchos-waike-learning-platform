import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { AdminHardeningPanel } from "../components/admin/AdminHardeningPanel";
import { InteropStatusPanel } from "../components/interop/InteropPanels";
import { DeviceProfilePanel } from "../components/device/DeviceProfilePanel";
import { createMockHubClient, resetMockHubStore } from "../lib/hub/mockHub";

afterEach(() => {
  cleanup();
  resetMockHubStore();
});

beforeEach(() => {
  resetMockHubStore();
});

describe("Gate C a11y — production App / admin / learner", () => {
  it("App exposes skip link and primary navigation landmarks", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /Skip to content/i })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: /Primary/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /WAIKE Learning OS/i })).toBeTruthy();
  });

  it("interop panel in App loads claims with live hub", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-instruct"));
    await user.click(screen.getByTestId("mode-interop"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Interoperability/i })).toBeTruthy();
      expect(screen.getByText(/NOT_FULL_ONEROSTER/)).toBeTruthy();
      expect(screen.getByText(/NOT_FULL_QTI/)).toBeTruthy();
    });
  });

  it("admin hardening workflows are real buttons wired to hub", async () => {
    const hub = createMockHubClient({ actorId: "admin-alpha", role: "site_admin" });
    const user = userEvent.setup();
    render(<AdminHardeningPanel workflows={["backup_restore", "privacy_controls"]} hub={hub} />);
    expect(screen.getByRole("button", { name: /backup restore/i })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /privacy controls/i }));
    await waitFor(() => {
      expect(screen.getByTestId("admin-hardening-result").textContent).toMatch(/youth_mode/);
    });
  });

  it("device profile list remains accessible", () => {
    render(
      <DeviceProfilePanel
        profiles={[
          { id: "student_14_5", name: 'Student 14.5"', research_role: "desk" },
          { id: "edge_io_wearables", name: "Edge IO Wearables", research_role: "HUD", companion_only: true },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: /Device Quartet/i })).toBeTruthy();
  });

  it("InteropStatusPanel exposes focusable claims without stub-only props", async () => {
    const hub = createMockHubClient({ actorId: "instructor-1", role: "instructor" });
    render(<InteropStatusPanel hub={hub} />);
    await waitFor(() => {
      expect(screen.getByTestId("interop-oneroster").textContent).toMatch(/NOT_FULL_ONEROSTER/);
    });
    expect(screen.getByRole("heading", { name: /Interoperability/i })).toBeTruthy();
  });
});
