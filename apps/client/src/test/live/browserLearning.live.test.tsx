/**
 * @vitest-environment jsdom
 *
 * The signed-in reader talks to a real loopback Hub. Fetch is not mocked.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BrowserLearning } from "../../components/learner/BrowserLearning";
import { PUBLIC_TRACKS, loadPublicContent } from "../../lib/product/publicCurriculum";
import { SECTION, hubUrl, login } from "./liveHub";

afterEach(cleanup);

describe("signed-in reader against the local Hub", () => {
  it("opens week 1, practices without a grade, receives source tutoring, and hides the other learner", async () => {
    await loadPublicContent(PUBLIC_TRACKS[0]);
    const alpha = await login("learner-alpha");
    render(
      <BrowserLearning
        trackId="DIGITAL_CONFIDENCE"
        unit={1}
        onNavigate={() => {}}
        auth={{ token: alpha.token, baseUrl: hubUrl(), sectionId: SECTION, onReview: () => {} }}
      />,
    );
    await waitFor(() => expect(screen.getByText("Progress is stored in lesson_progress. No grade was written.")).toBeInTheDocument());
    const lesson = screen.getByTestId("full-lesson-content").textContent || "";
    expect(lesson.length).toBeGreaterThan(80);

    const quizForm = document.querySelector("#practice-quiz form");
    expect(quizForm).not.toBeNull();
    quizForm!.querySelectorAll("fieldset").forEach((group) => {
      const choice = group.querySelector("input");
      if (choice) fireEvent.click(choice);
    });
    fireEvent.click(screen.getByRole("button", { name: "Check my answers" }));
    await waitFor(() => expect(screen.getByText(/Practice result: \d+ \/ \d+\. No grade was written\./)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Ask about this lesson"), { target: { value: "kiosk idle essay session" } });
    fireEvent.click(screen.getByRole("button", { name: "Request tutoring" }));
    await waitFor(
      () => expect(screen.getByText("Deterministic source text. modelCompletion is empty. This is not model inference. Inference is still blocked.")).toBeInTheDocument(),
      { timeout: 25_000 },
    );
    const tutoring = screen.getByTestId("source-tutoring").textContent || "";
    expect(tutoring.length).toBeGreaterThan(40);
    expect(tutoring).not.toMatch(/model inference/i);
    expect(lesson.includes(tutoring.slice(0, 80).trim()) || tutoring.includes("Source:")).toBe(true);

    const alphaPull = await alpha.req<{ lesson_progress: { user_id: string; lesson_id: string }[]; grades: unknown[] }>(
      `/api/v1/sync/pull?section_id=${encodeURIComponent(SECTION)}&since_revision=0`,
    );
    expect(alphaPull.lesson_progress.some((row) => row.user_id === alpha.userId && row.lesson_id === "w01")).toBe(true);
    expect(alphaPull.grades).toEqual([]);

    const beta = await login("learner-beta");
    const betaPull = await beta.req<{ lesson_progress: { user_id: string }[] }>(
      `/api/v1/sync/pull?section_id=${encodeURIComponent(SECTION)}&since_revision=0`,
    );
    expect(betaPull.lesson_progress.some((row) => row.user_id === alpha.userId)).toBe(false);
    const sectionBook = await beta.req<{ rows: { learner_id?: string }[] }>(`/api/v1/sections/${SECTION}/gradebook`);
    expect(sectionBook.rows.every((row) => row.learner_id !== alpha.userId)).toBe(true);
    await expect(beta.req(`/api/v1/instructor/assignments/DIGITAL_CONFIDENCE-independent-v1/queue`)).rejects.toMatchObject({ status: 403 });
  }, 40_000);
});
