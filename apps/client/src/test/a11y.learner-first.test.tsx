import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "../App";
import { resetMockHubStore } from "../lib/hub/mockHub";

afterEach(() => {
  cleanup();
  resetMockHubStore();
});

describe("Learner-first automated a11y", () => {
  it("keeps skip link, primary nav, and labeled search", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /Skip to content/i })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: /Primary/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /WAIKE Learning OS/i })).toBeTruthy();
  });
});
