import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "./App";

afterEach(() => {
  cleanup();
  delete (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__;
  delete (window as unknown as { __WAIKE_RESUME_OFFSET__?: number }).__WAIKE_RESUME_OFFSET__;
});

beforeEach(() => {
  delete (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__;
});

describe("WAIKE Learning OS shell", () => {
  it("renders branded shell and trust status", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /WAIKE Learning OS/i })).toBeInTheDocument();
    expect(screen.getByTestId("trust-banner")).toBeInTheDocument();
  });

  it("installs and shows verified trust", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    await waitFor(() => {
      expect(screen.getByTestId("trust-banner").textContent).toMatch(/Verified learner pack/i);
    });
  });

  it("opens a lesson from the course card", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    await user.click(screen.getByRole("button", { name: /Week 1/i }));
    expect(screen.getByTestId("lesson-body").textContent).toMatch(/Real lesson content/i);
  });

  it("persists resume hint after scroll save", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    await user.click(screen.getByRole("button", { name: /Week 1/i }));
    (window as unknown as { __WAIKE_RESUME_OFFSET__?: number }).__WAIKE_RESUME_OFFSET__ = 120;
    // trigger save via re-open path
    await user.click(screen.getByRole("button", { name: /Week 1/i }));
    await waitFor(() => {
      expect(screen.getByTestId("resume-hint").textContent).toMatch(/Resume DIGITAL_CONFIDENCE.W01/i);
    });
  });

  it("shows typed error for tampered pack", async () => {
    const user = userEvent.setup();
    (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__ = "TAMPERED_CONTENT";
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/TAMPERED_CONTENT/i);
    });
  });

  it("shows typed error for wrong role", async () => {
    const user = userEvent.setup();
    (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__ = "WRONG_ROLE";
    render(<App />);
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/WRONG_ROLE/i);
    });
  });

  it("supports keyboard focus on install CTA", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.tab(); // skip link
    await user.tab(); // install CTA
    expect(screen.getByRole("button", { name: /Install learner pack/i })).toHaveFocus();
  });
});
