/**
 * @vitest-environment jsdom
 *
 * Production activity UX driven through the real hub. The components below issue
 * genuine HTTP calls with real session tokens; nothing is stubbed.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { InstructorActivities } from "../../components/activities/InstructorActivities";
import { LearnerActivities } from "../../components/activities/LearnerActivities";
import {
  createActivityClient,
  createInstructorActivityClient,
  type ActivityClient,
  type InstructorActivityClient,
} from "../../lib/hub/activities";
import { SECTION, login, type LiveSession } from "./liveHub";

let learnerActivities: ActivityClient;
let staffActivities: ActivityClient;
let staff: InstructorActivityClient;
let learnerSession: LiveSession;
let staffSession: LiveSession;

function reqOf(session: LiveSession) {
  return <T,>(path: string, init?: RequestInit) => session.req<T>(path, init);
}

beforeAll(async () => {
  learnerSession = await login("learner-alpha");
  staffSession = await login("instructor-alpha");
  learnerActivities = createActivityClient(reqOf(learnerSession));
  staffActivities = createActivityClient(reqOf(staffSession));
  staff = createInstructorActivityClient(reqOf(staffSession));
});

afterEach(cleanup);

describe("learner activity screens", () => {
  it("renders real quizzes, labs and discussions instead of raw JSON", async () => {
    render(<LearnerActivities activities={learnerActivities} sectionId={SECTION} />);

    await screen.findByRole("region", { name: "Quizzes" });
    expect(screen.getByRole("region", { name: "Labs" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Discussions" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Groups" })).toBeInTheDocument();
    // A debug dump would show braces and quoted keys; a real UI does not.
    expect(document.body.textContent).not.toMatch(/"quiz_id"\s*:/);
  });

  it("never exposes an answer key on the learner path", async () => {
    render(<LearnerActivities activities={learnerActivities} sectionId={SECTION} />);
    await screen.findByRole("region", { name: "Quizzes" });
    expect(screen.queryByTestId("answer-key")).toBeNull();
    expect(document.body.textContent).not.toMatch(/answer key/i);
    // The learner client type has no answerKey method at all.
    expect((learnerActivities as unknown as Record<string, unknown>).answerKey).toBeUndefined();
    // And the route itself is refused for a learner session.
    await expect(
      learnerSession.req(`/api/v1/quizzes/quiz_dc_w01/answer-key`),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("takes a quiz end to end and shows the server-scored result", async () => {
    const user = userEvent.setup();
    render(<LearnerActivities activities={learnerActivities} sectionId={SECTION} />);

    const quizzes = await screen.findByRole("region", { name: "Quizzes" });
    const quizButtons = within(quizzes).getAllByRole("button");
    await user.click(quizButtons[0]);

    const start = await screen.findByRole("button", { name: /start attempt/i });
    await user.click(start);

    // Scope to the attempt itself so the discussion form's inputs are untouched.
    const attempt = await screen.findByRole("region", { name: /^Attempt for / });
    for (const group of within(attempt).queryAllByRole("group")) {
      const radios = within(group).queryAllByRole("radio");
      if (radios.length > 0) {
        await user.click(radios[0]);
        continue;
      }
      const box = within(group).queryAllByRole("textbox")[0];
      if (box) await user.type(box, "My reasoning for this answer.");
    }
    await user.click(within(attempt).getByRole("button", { name: /submit attempt/i }));

    const status = await screen.findByTestId("attempt-status", undefined, { timeout: 10_000 });
    expect(status.textContent).toMatch(/graded|submitted|awaiting|pending/i);
    expect(screen.getByTestId("attempt-score")).toBeInTheDocument();
  });

  it("shows an approved accommodation to the learner it belongs to", async () => {
    await staff.upsertAccommodation({
      learner_id: learnerSession.userId,
      section_id: SECTION,
      time_multiplier: 1.5,
      due_extension_minutes: 10,
    });
    render(<LearnerActivities activities={learnerActivities} sectionId={SECTION} />);
    const note = await screen.findByTestId("accommodation-note");
    expect(note.textContent).toMatch(/1\.5/);
  });
});

describe("instructor activity console", () => {
  it("shows grading progress and the manual queue", async () => {
    render(
      <InstructorActivities
        activities={staffActivities}
        staff={staff}
        sectionId={SECTION}
      />,
    );
    await screen.findByRole("region", { name: "Manual grading queue" });
    await waitFor(() => expect(screen.getByTestId("grading-progress")).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Answer keys" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Discussion moderation" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Accommodations" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Regrade" })).toBeInTheDocument();
  });

  it("reveals an answer key only to assigned staff", async () => {
    const user = userEvent.setup();
    render(
      <InstructorActivities activities={staffActivities} staff={staff} sectionId={SECTION} />,
    );
    const panel = await screen.findByRole("region", { name: "Answer keys" });
    const button = await within(panel).findByRole("button");
    await user.click(button);
    await waitFor(() => expect(screen.getByTestId("answer-key")).toBeInTheDocument());

    // The same key must never be reachable through the learner client.
    await expect(
      (learnerActivities as unknown as Record<string, unknown>).answerKey,
    ).toBeUndefined();
  });

  it("refuses staff calls for a section this instructor is not assigned to", async () => {
    await expect(staff.manualQueue("sec_beta_dc_w01")).rejects.toMatchObject({ status: 403 });
    await expect(
      staff.upsertAccommodation({
        learner_id: "learner-gamma",
        section_id: "sec_beta_dc_w01",
        time_multiplier: 3,
      }),
    ).rejects.toMatchObject({ status: 403 });
  });

  it("requires a reason before queueing a regrade", async () => {
    const user = userEvent.setup();
    render(
      <InstructorActivities activities={staffActivities} staff={staff} sectionId={SECTION} />,
    );
    const panel = await screen.findByRole("region", { name: "Regrade" });
    const queue = within(panel).getByRole("button", { name: /queue regrade/i });

    await user.click(queue);
    expect(await within(panel).findByRole("alert")).toHaveTextContent(/submission/i);

    await user.type(within(panel).getByLabelText(/submission/i), "sub_regrade_demo");
    await user.click(queue);
    expect(await within(panel).findByRole("alert")).toHaveTextContent(/reason is required/i);
  });
});
