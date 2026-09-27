import { describe, expect, it } from "vitest";
import { loadActiveCourseId, persistActiveCourseId, resolveActiveCourse, selectActiveCourse } from "./activeCourse";
import { filterAssignments, pickOpenAssignment } from "./assignmentCenter";
import { calendarFromAssignments, groupCalendar } from "./calendarTodo";
import { parseWaikeDeepLink } from "./deepLinks";
import { overallPercentAllowed } from "./gradesHonesty";
import { classifyIntervention, filterIntervention, previewDueDateShift } from "./instructorWorkflow";
import { resolveModuleStatus } from "./moduleStatus";
import { notificationsFromSignals } from "./notifications";
import { authorizeSearchHits, isAnswerKeyMaterial, matchQuery } from "./searchAuthz";
import { containsUnsafeHtml, renderSafeMarkdown } from "./safeMarkdown";
import { validateSchoolAppLaunch } from "./schoolApps";
import { studyModesForContent } from "./studyMode";
import { buildTodayState, sortDueSoon } from "./todayHome";
import type { AssignmentCardModel, CourseCardModel } from "./types";

const memory = new Map<string, string>();
const storage = {
  getItem: (k: string) => memory.get(k) ?? null,
  setItem: (k: string, v: string) => {
    memory.set(k, v);
  },
};

const courses: CourseCardModel[] = [
  { section_id: "sec_dc", code: "DC", title: "Digital Confidence" },
  { section_id: "sec_sb", code: "SB", title: "Software Builder" },
];

const assignments: AssignmentCardModel[] = [
  {
    assignment_id: "a1",
    section_id: "sec_dc",
    course_title: "Digital Confidence",
    title: "Reflection",
    due_at: "2026-09-28T18:00:00Z",
    submission_state: "not_started",
    grade_state: "none",
    filter_keys: ["all"],
  },
  {
    assignment_id: "a2",
    section_id: "sec_sb",
    course_title: "Software Builder",
    title: "Conflict report",
    due_at: "2026-09-20T18:00:00Z",
    submission_state: "not_started",
    grade_state: "none",
    filter_keys: ["all"],
  },
  {
    assignment_id: "a3",
    section_id: "sec_sb",
    course_title: "Software Builder",
    title: "Returned lab",
    due_at: "2026-09-30T18:00:00Z",
    submission_state: "returned",
    grade_state: "returned",
    filter_keys: ["all"],
  },
];

describe("active course persistence", () => {
  it("does not default to list[0]", () => {
    expect(resolveActiveCourse(courses, null)).toBeNull();
    expect(selectActiveCourse(courses, "missing")).toBeNull();
    const chosen = selectActiveCourse(courses, "sec_sb", (id) => persistActiveCourseId(id, storage));
    expect(chosen?.title).toBe("Software Builder");
    expect(loadActiveCourseId(storage)).toBe("sec_sb");
    expect(resolveActiveCourse(courses, "sec_sb")?.section_id).toBe("sec_sb");
  });
});

describe("today ordering", () => {
  it("sorts due soon and flags overdue without shame copy", () => {
    const now = "2026-09-26T12:00:00Z";
    const due = sortDueSoon(assignments, now);
    expect(due.map((x) => x.assignment_id)).toEqual(["a1", "a3"]);
    const today = buildTodayState({
      courses,
      assignments,
      calendar: calendarFromAssignments(assignments, now),
      feedback: [
        {
          feedback_id: "f1",
          body: "Clear example",
          created_at: "2026-09-25T12:00:00Z",
          section_id: "sec_sb",
          course_title: "Software Builder",
          assignment_id: "a3",
        },
      ],
      active: courses[1],
      continueItem: {
        section_id: "sec_sb",
        course_title: "Software Builder",
        item_title: "Week 1",
        item_kind: "lesson",
        item_id: "SB.W01",
        progress_label: "In progress",
      },
      nowIso: now,
    });
    expect(today.due_soon[0].assignment_id).toBe("a1");
    expect(today.needs_attention.some((x) => x.kind === "overdue" && x.id.includes("a2"))).toBe(true);
    expect(today.recent_feedback[0].feedback_id).toBe("f1");
    expect(today.ask_context.section_id).toBe("sec_sb");
  });
});

describe("assignment center", () => {
  it("does not open the first assignment by default", () => {
    expect(pickOpenAssignment(assignments, null)).toBeNull();
    expect(pickOpenAssignment(assignments, "a2")?.title).toBe("Conflict report");
    const now = "2026-09-26T12:00:00Z";
    expect(filterAssignments(assignments, "missing_overdue", now).map((x) => x.assignment_id)).toEqual(["a2"]);
    expect(filterAssignments(assignments, "returned", now).map((x) => x.assignment_id)).toEqual(["a3"]);
  });
});

describe("calendar", () => {
  it("groups timezone-safe buckets and deep links", () => {
    const now = "2026-09-26T12:00:00Z";
    const items = calendarFromAssignments(assignments, now);
    const groups = groupCalendar(items, now, "UTC");
    expect(groups.overdue.map((x) => x.id)).toEqual(["a2"]);
    expect(groups.today.concat(groups.this_week, groups.later).every((x) => x.deep_link.startsWith("waike://assignment/"))).toBe(true);
  });
});

describe("safe markdown", () => {
  it("renders structure and strips script/javascript", () => {
    const html = renderSafeMarkdown(
      `# Title\n\nHello **world**\n\n- one\n\n[ok](https://example.edu)\n\n[bad](javascript:alert(1))\n\n\`\`\`js\nalert(1)\n\`\`\`\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![Lab photo](https://cdn.example.edu/lab.png)\n\n> [!NOTE] Wear safety glasses\n`,
    );
    expect(html).toContain("<h1>Title</h1>");
    expect(html).toContain("<strong>world</strong>");
    expect(html).toContain("<ul>");
    expect(html).toContain('href="https://example.edu"');
    expect(html).not.toContain("javascript:alert");
    expect(html).toContain("<table>");
    expect(html).toContain('alt="Lab photo"');
    expect(html).toContain("md-callout");
    expect(html).toContain("<pre><code");
    expect(containsUnsafeHtml('<script>alert(1)</script>')).toBe(true);
    expect(renderSafeMarkdown("<script>alert(1)</script>")).not.toContain("<script>");
  });
});

describe("search authz", () => {
  it("denies answer keys and other sections", () => {
    expect(isAnswerKeyMaterial("Week 1 answer key")).toBe(true);
    const hits = matchQuery("week", [
      { id: "1", kind: "lesson", title: "Week 1", snippet: "git conflict", section_id: "sec_sb" },
      { id: "2", kind: "resource", title: "Instructor answer key", snippet: "key", section_id: "sec_sb" },
      { id: "3", kind: "lesson", title: "Week 1 other site", snippet: "secret", section_id: "sec_other" },
    ]);
    const allowed = authorizeSearchHits(hits, ["sec_sb"], "learner");
    expect(allowed.map((x) => x.id)).toEqual(["1"]);
  });
});

describe("grades honesty", () => {
  it("hides overall percent when weighting is not modeled", () => {
    expect(overallPercentAllowed({ weightingModeled: false, overallPercent: 92 })).toBeNull();
    expect(overallPercentAllowed({ weightingModeled: true, overallPercent: 92 })).toBe(92);
  });
});

describe("study / instructor / school apps / deep links / notifications", () => {
  it("labels study modes honestly", () => {
    const modes = studyModesForContent({
      hasReadableText: true,
      ttsAvailable: true,
      authoredPractice: false,
      authoredFlashcards: false,
      labLaunchable: true,
      masteryEvidence: false,
    });
    expect(modes.find((m) => m.id === "listen")?.honesty).toMatch(/Not studio narration/);
    expect(modes.find((m) => m.id === "practice")?.honesty).toMatch(/labeled drafts/);
  });

  it("previews due shift and does not treat waiting-for-grade as failure", () => {
    const preview = previewDueDateShift([{ id: "a1", title: "Reflection", current_due: "2026-09-28T18:00:00Z" }], 24);
    expect(preview[0].proposed_due).toBe("2026-09-29T18:00:00.000Z");
    const row = classifyIntervention({
      learner_id: "l1",
      display_name: "Ada",
      missingWork: false,
      lowMastery: false,
      revisionRequested: false,
      inactivityTrusted: false,
      waitingForInstructorGrade: true,
    });
    expect(row).toBeNull();
    expect(filterIntervention([], "missing_work")).toEqual([]);
  });

  it("enforces institution-configured school app origins", () => {
    const app = {
      app_id: "portal",
      label: "Portal",
      launch_kind: "browser_url" as const,
      url: "https://portal.example.edu/apps",
      allowed_origins: ["https://portal.example.edu"],
      pinned: false,
      configured_by: "institution" as const,
      captures_credentials: false as const,
    };
    expect(validateSchoolAppLaunch(app, "https://portal.example.edu/apps").ok).toBe(true);
    expect(validateSchoolAppLaunch(app, "https://evil.example/apps").ok).toBe(false);
  });

  it("parses waike deep links", () => {
    expect(parseWaikeDeepLink("waike://assignment/a2")?.mode).toBe("assignments");
    expect(parseWaikeDeepLink("waike://course/sec_sb")?.id).toBe("sec_sb");
    expect(parseWaikeDeepLink("https://example.edu")).toBeNull();
  });

  it("builds notification deep links", () => {
    const notes = notificationsFromSignals({
      returned: [{ id: "a3", title: "Returned lab", at: "2026-09-25T12:00:00Z", deep_link: "waike://assignment/a3" }],
    });
    expect(notes[0].deep_link).toBe("waike://assignment/a3");
    expect(notes[0].unread).toBe(true);
  });

  it("does not invent module completion", () => {
    expect(resolveModuleStatus({ started: false, submitted: false, needsReview: false, complete: false, lockedByPrerequisite: false })).toBe("not_started");
    expect(resolveModuleStatus({ started: true, submitted: false, needsReview: false, complete: false, lockedByPrerequisite: false })).toBe("in_progress");
  });
});
