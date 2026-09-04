import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "../App";
import { resetMockHubStore } from "../lib/hub/mockHub";

afterEach(() => {
  cleanup();
  resetMockHubStore();
});

describe("PR3 automated accessibility smoke (not certification)", () => {
  it("exposes skip link, branded heading, and primary navigation", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /Skip to content/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /WAIKE Learning OS/i })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /Primary/i })).toBeInTheDocument();
  });

  it("has no production actor-switcher chip", () => {
    render(<App />);
    expect(screen.queryByTestId("actor-chip")).not.toBeInTheDocument();
    expect(screen.getByTestId("session-chip")).toBeInTheDocument();
  });

  it("grade/queue surfaces use labeled controls when opened via mock", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-instruct"));
    expect(screen.getByTestId("instructor-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("instructor-queue")).toBeInTheDocument();
  });
});
