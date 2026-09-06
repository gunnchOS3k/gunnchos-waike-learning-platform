import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { InteropStatusPanel } from "../components/interop/InteropPanels";
import { DeviceProfilePanel } from "../components/device/DeviceProfilePanel";
import { AdminHardeningPanel } from "../components/admin/AdminHardeningPanel";

afterEach(() => cleanup());

describe("Gate C a11y landmarks", () => {
  it("exposes interop heading and focusable claims", () => {
    render(
      <InteropStatusPanel
        oneroster={{ claim: "NOT_FULL_ONEROSTER" }}
        qti={{ claim: "NOT_FULL_QTI" }}
        lti={{ claim: "NOT_LTI_CERTIFIED" }}
      />,
    );
    expect(screen.getByRole("heading", { name: /Interoperability/i })).toBeTruthy();
    expect(screen.getByText(/NOT_FULL_ONEROSTER/)).toBeTruthy();
  });

  it("exposes device profile list", () => {
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

  it("admin workflows are buttons", () => {
    render(<AdminHardeningPanel workflows={["backup_restore", "privacy_controls"]} />);
    expect(screen.getByRole("button", { name: /backup restore/i })).toBeTruthy();
  });
});
