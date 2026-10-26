/**
 * @vitest-environment jsdom
 *
 * The installed client application against a real loopback Hub. Fetch is not mocked.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { PUBLIC_TRACKS, loadPublicContent } from "../../lib/product/publicCurriculum";
import { FIXTURE_PASSWORD, hubUrl } from "./liveHub";

const EVIDENCE = "Alpha private evidence for the gradebook.";
const FEEDBACK = "Returned only to the submitting learner.";
const HUB_STATE = join(tmpdir(), "waike-live-hub-state.json");

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

describe("real client journeys on the local Hub", () => {
  it("signs out into another identity, resumes after restart, and keeps the grade with the learner", async () => {
    await loadPublicContent(PUBLIC_TRACKS[0]);
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("login-form")).toBeInTheDocument());
    await signIn("learner-alpha");

    await waitFor(() => expect(screen.getByRole("button", { name: /Digital Confidence — Alpha/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Digital Confidence — Alpha/ }));
    fireEvent.click(screen.getByRole("button", { name: "Open Digital Confidence weekly reader" }));
    await waitFor(() => expect(screen.getByText("Progress is stored in lesson_progress. No grade was written.")).toBeInTheDocument(), { timeout: 20_000 });

    document.querySelectorAll("#practice-quiz form fieldset").forEach((group) => {
      const choice = group.querySelector("input");
      if (choice) fireEvent.click(choice);
    });
    fireEvent.click(screen.getByRole("button", { name: "Check my answers" }));
    await waitFor(() => expect(screen.getByText(/Practice result: \d+ \/ \d+\. No grade was written\./)).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("mode-assignments"));
    await waitFor(() => expect(screen.getByTestId("open-assignment-digital_confidence_w01")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("draft-text"), { target: { value: EVIDENCE } });
    fireEvent.click(screen.getByTestId("submit-btn"));
    await waitFor(() => expect(screen.getByTestId("assignment-status")).toHaveTextContent(/Submitted/));
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-feedback")).not.toBeInTheDocument();

    await signOut();
    expect(screen.queryByTestId("submit-btn")).not.toBeInTheDocument();
    const anonymous = await fetch(`${hubUrl()}/api/v1/assignments/digital_confidence_w01/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "anonymous-write", text_response: "must not persist" }),
    });
    expect(anonymous.status).toBe(401);

    await signIn("learner-beta");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(EVIDENCE)).not.toBeInTheDocument();
    expect(screen.queryByText(FEEDBACK)).not.toBeInTheDocument();
    await signOut();

    await signIn("instructor-alpha");
    const queued = await screen.findAllByRole("button", { name: /learner-alpha · attempt/ });
    fireEvent.click(queued[queued.length - 1]);
    await waitFor(() => expect(screen.getByTestId("grade-panel")).toHaveTextContent(EVIDENCE));
    fireEvent.change(screen.getByTestId("feedback-text"), { target: { value: FEEDBACK } });
    fireEvent.click(screen.getByTestId("return-grade-btn"));
    await waitFor(() => expect(screen.getByTestId("instructor-status")).toHaveTextContent(/Graded/));
    await signOut();

    await restartHub();
    await signIn("learner-alpha");
    fireEvent.click(await screen.findByRole("button", { name: /Digital Confidence — Alpha/ }));
    fireEvent.click(screen.getByRole("button", { name: "Open Digital Confidence weekly reader" }));
    await waitFor(() => expect(screen.getByTestId("resumed-progress")).toHaveTextContent("Resumed stored lesson progress for w01"), { timeout: 20_000 });

    fireEvent.click(screen.getByTestId("mode-assignments"));
    const card = await screen.findByTestId("open-assignment-digital_confidence_w01");
    expect(card.textContent).toMatch(/returned/i);
    fireEvent.click(card);
    await waitFor(() => expect(screen.getByTestId("learner-feedback")).toHaveTextContent(FEEDBACK));
    expect(screen.getByTestId("learner-grade").textContent).toMatch(/10/);
    expect(screen.getByTestId("gradebook-list").textContent).toMatch(/10/);
    await signOut();

    await signIn("learner-beta");
    fireEvent.click(await screen.findByRole("button", { name: /Digital Confidence — Alpha/ }));
    fireEvent.click(screen.getByRole("button", { name: "Open Digital Confidence weekly reader" }));
    await waitFor(() => expect(screen.getByText("Progress is stored in lesson_progress. No grade was written.")).toBeInTheDocument(), { timeout: 20_000 });
    expect(screen.queryByTestId("resumed-progress")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(EVIDENCE)).not.toBeInTheDocument();
    expect(screen.queryByText(FEEDBACK)).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
  }, 120_000);

  it("opens the on-disk General IT week without a practice grade and keeps the return with Alpha", async () => {
    const evidence = "Alpha General IT evidence for the operator desk.";
    const feedback = "Returned only to the General IT learner.";
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("login-form")).toBeInTheDocument());
    await signIn("learner-alpha");

    fireEvent.click(await screen.findByRole("button", { name: /General IT — Operator to Support Specialist/ }));
    fireEvent.click(screen.getByTestId("open-general-it-reader"));
    await waitFor(() => expect(screen.getByText("Progress is stored in lesson_progress. No grade was written.")).toBeInTheDocument(), { timeout: 20_000 });
    expect(screen.getByTestId("full-lesson-content").textContent).toMatch(/Civic Tech Desk/);

    document.querySelectorAll("#practice-quiz form fieldset").forEach((group) => {
      const choice = group.querySelector("input");
      if (choice) fireEvent.click(choice);
    });
    fireEvent.click(screen.getByRole("button", { name: "Check my answers" }));
    await waitFor(() => expect(screen.getByText(/Practice result: \d+ \/ \d+\. No grade was written\./)).toBeInTheDocument());
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("mode-assignments"));
    await waitFor(() => expect(screen.getByTestId("open-assignment-general_it_w01")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("open-assignment-general_it_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("draft-text"), { target: { value: evidence } });
    fireEvent.click(screen.getByTestId("submit-btn"));
    await waitFor(() => expect(screen.getByTestId("assignment-status")).toHaveTextContent(/Submitted/));
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-feedback")).not.toBeInTheDocument();

    await signOut();
    const anonymous = await fetch(`${hubUrl()}/api/v1/assignments/general_it_w01/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "anonymous-general-it", text_response: "must not persist", section_id: "sec_alpha_git_w01" }),
    });
    expect(anonymous.status).toBe(401);

    await signIn("learner-beta");
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId("open-assignment-general_it_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(evidence)).not.toBeInTheDocument();
    expect(screen.queryByText(feedback)).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
    await signOut();

    await signIn("instructor-alpha");
    const queued = await screen.findAllByTestId((id) => id.startsWith("queue-item-general_it_w01-"));
    fireEvent.click(queued[queued.length - 1]);
    await waitFor(() => expect(screen.getByTestId("grade-panel")).toHaveTextContent(evidence));
    fireEvent.change(screen.getByTestId("feedback-text"), { target: { value: feedback } });
    fireEvent.click(screen.getByTestId("return-grade-btn"));
    await waitFor(() => expect(screen.getByTestId("instructor-status")).toHaveTextContent(/Graded/));
    await signOut();

    await restartHub();
    await signIn("learner-alpha");
    fireEvent.click(await screen.findByRole("button", { name: /General IT — Operator to Support Specialist/ }));
    fireEvent.click(screen.getByTestId("open-general-it-reader"));
    await waitFor(() => expect(screen.getByTestId("resumed-progress")).toHaveTextContent("Resumed stored lesson progress for w01"), { timeout: 20_000 });

    fireEvent.click(screen.getByTestId("mode-assignments"));
    const card = await screen.findByTestId("open-assignment-general_it_w01");
    expect(card.textContent).toMatch(/returned/i);
    fireEvent.click(card);
    await waitFor(() => expect(screen.getByTestId("learner-feedback")).toHaveTextContent(feedback));
    expect(screen.getByTestId("learner-grade").textContent).toMatch(/10/);
    await signOut();

    await signIn("learner-beta");
    fireEvent.click(await screen.findByRole("button", { name: /General IT — Operator to Support Specialist/ }));
    fireEvent.click(screen.getByTestId("open-general-it-reader"));
    await waitFor(() => expect(screen.getByText("Progress is stored in lesson_progress. No grade was written.")).toBeInTheDocument(), { timeout: 20_000 });
    expect(screen.queryByTestId("resumed-progress")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("mode-assignments"));
    fireEvent.click(await screen.findByTestId("open-assignment-general_it_w01"));
    await waitFor(() => expect(screen.getByTestId("draft-text")).toHaveValue(""));
    expect(screen.queryByText(evidence)).not.toBeInTheDocument();
    expect(screen.queryByText(feedback)).not.toBeInTheDocument();
    expect(screen.queryByTestId("learner-grade")).not.toBeInTheDocument();
  }, 120_000);
});
