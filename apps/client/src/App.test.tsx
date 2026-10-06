import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { resetMockHubStore } from "./lib/hub/mockHub";

afterEach(() => {
  cleanup();
  resetMockHubStore();
  delete (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__;
  delete (window as unknown as { __WAIKE_RESUME_OFFSET__?: number }).__WAIKE_RESUME_OFFSET__;
  vi.unstubAllEnvs();
});

beforeEach(() => {
  resetMockHubStore();
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

  it("keeps all 18 tracks discoverable without a Hub and does not fake school state", async () => {
    vi.stubEnv("VITE_PIXEL_PILOT", "true");
    vi.stubEnv("VITE_HUB_URL", "");
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("public-catalog-banner")).toHaveTextContent(/all 18/i);
    });
    expect(screen.getByTestId("public-runtime-truth")).toHaveTextContent(/complete packaged curriculum/i);

    await user.click(screen.getByTestId("mode-courses"));
    expect(document.querySelectorAll('[data-testid^="course-card-"]')).toHaveLength(18);
    expect(screen.getByRole("heading", { name: "Digital Confidence to Computer Operator" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Data Visualization and Business Intelligence" })).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Open course" })[1]);
    expect(screen.getByTestId("course-home")).toHaveTextContent(/IT Support and Hardware Foundations/);
    expect(screen.getByTestId("module-sequence")).toHaveTextContent(/Assignment A01/);
    expect(screen.getByTestId("module-sequence")).toHaveTextContent(/lab_accessibility_contrast_check/);

    await user.click(screen.getByRole("button", { name: /Lesson: Week 1 presentation/ }));
    expect(screen.getByTestId("study-mode")).toHaveTextContent(/Idle policy 1200s/);

    await user.click(screen.getByTestId("mode-assignments"));
    await user.click(screen.getByRole("button", { name: /Assignment A01/i }));
    expect(screen.getByTestId("public-assignment-content")).toHaveTextContent(/ticket 4417/i);
    expect(screen.getByTestId("public-assignment-preview")).toHaveTextContent(/No submission has been created/i);

    await user.click(screen.getByTestId("mode-activities"));
    await user.click(screen.getByRole("button", { name: /lab_accessibility_contrast_check/i }));
    expect(screen.getByTestId("public-activity-content")).toHaveTextContent(/contrast/i);

    await user.click(screen.getByTestId("mode-more"));
    await user.click(screen.getByTestId("mode-grades"));
    expect(screen.getByTestId("public-grades-truth")).toHaveTextContent(/no school Hub is configured/i);
    expect(screen.queryByTestId("mode-gradebook")).not.toBeInTheDocument();
  });

  it("does not simulate a signed pack install in the public browser", async () => {
    vi.stubEnv("VITE_PIXEL_PILOT", "true");
    vi.stubEnv("VITE_HUB_URL", "");
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("public-catalog-banner")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /Install learner pack/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/does not pretend to install/i);
    expect(screen.getByTestId("trust-banner")).not.toHaveTextContent(/Verified learner pack/i);
  });

  it("runs learner assignment draft submit and instructor grade path", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByTestId("hub-mode-chip").textContent).toMatch(/hub:mock/);
    await user.click(screen.getByTestId("mode-assignments"));
    await waitFor(() => {
      expect(screen.getByTestId("assignment-center")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("assignment-body")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => {
      expect(screen.getByTestId("assignment-workspace")).toBeInTheDocument();
    });
    expect(screen.getByTestId("assignment-body").textContent).toMatch(/digital confidence/i);
    const draft = screen.getByTestId("draft-text");
    await user.clear(draft);
    await user.type(draft, "Community reflection draft");
    await waitFor(() => {
      expect(screen.getByTestId("draft-meta").textContent).toMatch(/Draft rev/i);
    });
    await user.click(screen.getByTestId("submit-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("receipt-card")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("mode-instruct"));
    await waitFor(() => {
      expect(screen.getByTestId("instructor-queue")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("force-gap")).not.toBeInTheDocument();
    expect(screen.queryByTestId("actor-chip")).not.toBeInTheDocument();
    expect(screen.getByTestId("session-chip")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /learner-a · attempt 1/i }));
    expect(screen.getByTestId("criterion-scores")).toBeInTheDocument();
    await user.click(screen.getByTestId("return-grade-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("instructor-status").textContent).toMatch(/Graded/i);
    });

    await user.click(screen.getByTestId("mode-assignments"));
    await user.click(screen.getByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => {
      expect(screen.getByTestId("remediation-list").textContent).toMatch(/assigned|Revise/i);
    });
  });
});
