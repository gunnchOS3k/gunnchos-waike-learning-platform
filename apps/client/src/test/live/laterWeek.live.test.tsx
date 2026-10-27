/**
 * @vitest-environment jsdom
 *
 * Software Builder week 2 on the real loopback Hub. Week 1 coverage is not this test.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { campusReturnHref } from "../../components/learner/BrowserLearning";
import { PUBLIC_TRACKS, loadPublicContent } from "../../lib/product/publicCurriculum";
import { FIXTURE_PASSWORD, hubUrl } from "./liveHub";

const HUB_STATE = join(tmpdir(), "waike-live-hub-state.json");
const TRACK = PUBLIC_TRACKS.find((track) => track.trackId === "SOFTWARE_BUILDER");
const ASSIGNMENT = "software_builder_w02";
const SECTION = "sec_alpha_software_builder_w01";
const EVIDENCE = "Alpha Software Builder week 2 checkout cases.";
const REVISION = "Alpha revised the checkout cases after the return.";
const FEEDBACK = "Returned only to the Software Builder learner.";
const REVISED_FEEDBACK = "Revision returned only to the Software Builder learner.";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllEnvs();
});

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.stubEnv("VITE_HUB_URL", hubUrl());
  vi.stubEnv("VITE_PUBLIC_READER", "");
  vi.stubEnv("VITE_WAIKE_MOCK_HUB", "");
});

async function signIn(username: string): Promise<void> {
  fireEvent.change(screen.getByTestId("login-username"), { target: { value: username } });
  fireEvent.change(screen.getByTestId("login-password"), { target: { value: FIXTURE_PASSWORD } });
  fireEvent.click(screen.getByTestId("login-submit"));
  await waitFor(() => expect(screen.getByTestId("logout-btn")).toBeInTheDocument());
}

async function signOut(): Promise<void> {
  fireEvent.click(screen.getByTestId("logout-btn"));
  await waitFor(() => expect(screen.getByTestId("login-form")).toBeInTheDocument());
}

async function restartHub(): Promise<void> {
  const state = JSON.parse(readFileSync(HUB_STATE, "utf8")) as {
    pid: number;
    db: string;
    port: number;
    baseUrl: string;
    python: string;
    script: string;
    cwd: string;
  };
  try {
    process.kill(state.pid, "SIGTERM");
  } catch {
    /* the first process already exited */
  }
  const down = Date.now() + 8_000;
  while (Date.now() < down) {
    try {
      await fetch(`${state.baseUrl}/healthz`);
      await new Promise((r) => setTimeout(r, 200));
    } catch {
      break;
    }
  }
  await new Promise((r) => setTimeout(r, 400));
  const child = spawn(
    state.python,
    [state.script, "--host", "127.0.0.1", "--port", String(state.port), "--db", state.db],
    { cwd: state.cwd, stdio: "ignore", env: process.env },
  );
  writeFileSync(HUB_STATE, JSON.stringify({ ...state, pid: child.pid }));
  const up = Date.now() + 20_000;
  while (Date.now() < up) {
    try {
      const res = await fetch(`${state.baseUrl}/healthz`);
      if (res.ok) return;
    } catch {
      /* still binding */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("hub did not resume");
}

describe("Software Builder week 2 on the local Hub", () => {
  it("allows a campus return only to https://gunnchos.com", () => {
    expect(campusReturnHref("?return=https://gunnchos.com")).toBe("https://gunnchos.com");
    expect(campusReturnHref("?return=https://evil.example")).toBeNull();
    expect(campusReturnHref("?return=https://gunnchos.com&next=1")).toBeNull();
    expect(campusReturnHref("")).toBeNull();
  });

  it("opens week 2, practices, revises the returned assessment, and keeps completion after restart", async () => {
    if (!TRACK) throw new Error("Software Builder is not in the public reader");
    window.history.replaceState({}, "", "/?return=https%3A%2F%2Fgunnchos.com");
    await loadPublicContent(TRACK);
    const courseButton = (name: string) => name === TRACK.title || name.startsWith(`${TRACK.title} ·`);
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("login-form")).toBeInTheDocument());
    await signIn("learner-alpha");

    fireEvent.click(await screen.findByRole("button", { name: courseButton }));
    fireEvent.click(screen.getByTestId("open-track-reader"));
    await waitFor(() => expect(screen.getByTestId("campus-return")).toHaveAttribute("href", "https://gunnchos.com"), { timeout: 20_000 });
    fireEvent.change(screen.getByLabelText("Choose unit"), { target: { value: "2" } });
    await waitFor(() => expect(screen.getByTestId("full-lesson-content")).toHaveTextContent(/REST for checkout/), { timeout: 20_000 });
    expect(screen.getByTestId("campus-return")).toHaveAttribute("href", "https://gunnchos.com");

    document.querySelectorAll("#practice-quiz form fieldset").forEach((group) => {
      const choice = group.querySelector("input");
      if (choice) fireEvent.click(choice);
    });
    fireEvent.click(screen.getByRole("button", { name: "Check my answers" }));
    await waitFor(() => expect(screen.getByText(/Practice result: \d+ \/ \d+\. No grade was written\./)).toBeInTheDocument(), { timeout: 20_000 });
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/My private draft/), { target: { value: EVIDENCE } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft on this device" }));
    expect(screen.getByTestId("campus-return")).toHaveAttribute("href", "https://gunnchos.com");
    fireEvent.click(screen.getByRole("button", { name: "Mark this lesson read" }));
    await waitFor(() => expect(screen.getByText("Lesson w02 is complete. No grade was written.")).toBeInTheDocument(), { timeout: 20_000 });

    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("draft-text"), { target: { value: EVIDENCE } });
    fireEvent.click(screen.getByTestId("submit-btn"));
    await waitFor(() => expect(screen.getByTestId("assignment-status")).toHaveTextContent(/Submitted/), { timeout: 20_000 });
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();

    const anonymous = await fetch(`${hubUrl()}/api/v1/assignments/${ASSIGNMENT}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: `anonymous-${ASSIGNMENT}`,
        text_response: "must not persist",
        section_id: SECTION,
      }),
    });
    expect(anonymous.status).toBe(401);
    await signOut();

    await signIn("learner-beta");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(EVIDENCE)).not.toBeInTheDocument();
    await signOut();

    await signIn("instructor-alpha");
    await waitFor(() => {
      expect(document.querySelector(`[data-testid^='queue-item-${ASSIGNMENT}-']`)).toBeTruthy();
    }, { timeout: 20_000 });
    const queued = document.querySelector(`[data-testid^='queue-item-${ASSIGNMENT}-']`);
    if (!(queued instanceof HTMLButtonElement)) throw new Error("week 2 queue item was not a button");
    fireEvent.click(queued);
    await waitFor(() => expect(screen.getByTestId("grade-panel")).toHaveTextContent(EVIDENCE));
    fireEvent.change(screen.getByTestId("feedback-text"), { target: { value: FEEDBACK } });
    fireEvent.click(screen.getByTestId("return-grade-btn"));
    await waitFor(() => expect(screen.getByTestId("instructor-status")).toHaveTextContent(/Graded/), { timeout: 20_000 });
    await signOut();

    await signIn("learner-alpha");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("learner-feedback")).toHaveTextContent(FEEDBACK));
    expect(screen.queryByText(REVISED_FEEDBACK)).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("draft-text"), { target: { value: REVISION } });
    fireEvent.click(screen.getByTestId("submit-btn"));
    await waitFor(() => expect(screen.getByText(/Attempt 2/)).toBeInTheDocument(), { timeout: 20_000 });
    await signOut();

    await signIn("learner-beta");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(REVISION)).not.toBeInTheDocument();
    expect(screen.queryByText(FEEDBACK)).not.toBeInTheDocument();
    await signOut();

    await signIn("instructor-alpha");
    await waitFor(() => {
      expect(screen.getByText(/attempt 2/)).toBeInTheDocument();
    }, { timeout: 20_000 });
    fireEvent.click(screen.getByText(/attempt 2/));
    await waitFor(() => expect(screen.getByTestId("grade-panel")).toHaveTextContent(REVISION));
    fireEvent.change(screen.getByTestId("feedback-text"), { target: { value: REVISED_FEEDBACK } });
    fireEvent.click(screen.getByTestId("return-grade-btn"));
    await waitFor(() => expect(screen.getByTestId("instructor-status")).toHaveTextContent(/Graded/), { timeout: 20_000 });
    await signOut();

    await restartHub();
    await signIn("learner-alpha");
    fireEvent.click(await screen.findByRole("button", { name: courseButton }));
    fireEvent.click(screen.getByTestId("open-track-reader"));
    fireEvent.change(screen.getByLabelText("Choose unit"), { target: { value: "2" } });
    await waitFor(() => expect(screen.getByTestId("resumed-progress")).toHaveTextContent("Resumed stored lesson progress for w02"), { timeout: 20_000 });
    await waitFor(() => expect(screen.getByText("Lesson w02 is complete. No grade was written.")).toBeInTheDocument());
    expect(screen.getByTestId("campus-return")).toHaveAttribute("href", "https://gunnchos.com");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    await waitFor(() => {
      expect(screen.getByTestId(`open-assignment-${ASSIGNMENT}`).textContent).toMatch(/returned/i);
    }, { timeout: 20_000 });
    fireEvent.click(screen.getByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("learner-feedback")).toHaveTextContent(REVISED_FEEDBACK));
    await signOut();

    await signIn("learner-beta");
    fireEvent.click(await screen.findByRole("button", { name: courseButton }));
    fireEvent.click(screen.getByTestId("open-track-reader"));
    fireEvent.change(screen.getByLabelText("Choose unit"), { target: { value: "2" } });
    await waitFor(() => expect(screen.getByTestId("full-lesson-content")).toHaveTextContent(/REST for checkout/), { timeout: 20_000 });
    expect(screen.queryByTestId("resumed-progress")).not.toBeInTheDocument();
    expect(screen.queryByText("Lesson w02 is complete. No grade was written.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId(`open-assignment-${ASSIGNMENT}`));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(REVISION)).not.toBeInTheDocument();
    expect(screen.queryByText(REVISED_FEEDBACK)).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
  }, 180_000);
});
