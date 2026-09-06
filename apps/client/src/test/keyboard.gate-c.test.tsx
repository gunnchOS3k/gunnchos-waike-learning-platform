import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { AdminHardeningPanel } from "../components/admin/AdminHardeningPanel";
import { InteropStatusPanel } from "../components/interop/InteropPanels";

afterEach(() => cleanup());

describe("Gate C keyboard-only", () => {
  it("tabs through admin workflow buttons", async () => {
    const user = userEvent.setup();
    render(<AdminHardeningPanel workflows={["backup_restore", "diagnostics"]} />);
    await user.tab();
    expect(screen.getByRole("button", { name: /backup restore/i })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: /diagnostics/i })).toHaveFocus();
  });

  it("interop claims are keyboard focusable", async () => {
    const user = userEvent.setup();
    render(
      <InteropStatusPanel
        oneroster={{ claim: "NOT_FULL_ONEROSTER" }}
        qti={{ claim: "NOT_FULL_QTI" }}
        lti={{ claim: "NOT_LTI_CERTIFIED" }}
      />,
    );
    await user.tab();
    expect(document.activeElement?.textContent).toMatch(/OneRoster/);
  });
});
