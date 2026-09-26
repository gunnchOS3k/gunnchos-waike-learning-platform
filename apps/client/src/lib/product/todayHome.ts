import type {
  AssignmentCardModel,
  AttentionItem,
  CalendarItem,
  CourseCardModel,
  FeedbackItem,
  TodayContinue,
  TodayState,
} from "./types";

export function sortDueSoon(items: AssignmentCardModel[], nowIso: string): AssignmentCardModel[] {
  const now = Date.parse(nowIso);
  return items
    .filter((item) => item.due_at && Date.parse(item.due_at) >= now)
    .sort((a, b) => Date.parse(a.due_at as string) - Date.parse(b.due_at as string));
}

export function isOverdue(dueAt: string | null, nowIso: string, authoritativeOverdue?: boolean): boolean {
  if (authoritativeOverdue === true) return true;
  if (!dueAt) return false;
  return Date.parse(dueAt) < Date.parse(nowIso);
}

export function buildNeedsAttention(args: {
  assignments: AssignmentCardModel[];
  nowIso: string;
  syncConflicts?: Array<{ id: string; title: string; section_id: string; course_title: string }>;
  lowMastery?: Array<{ id: string; title: string; section_id: string; course_title: string }>;
  unacknowledged?: Array<{ id: string; title: string; section_id: string; course_title: string }>;
}): AttentionItem[] {
  const out: AttentionItem[] = [];
  for (const a of args.assignments) {
    if (isOverdue(a.due_at, args.nowIso) && a.submission_state !== "submitted" && a.submission_state !== "returned") {
      out.push({
        id: `overdue:${a.assignment_id}`,
        kind: "overdue",
        title: a.title,
        course_title: a.course_title,
        section_id: a.section_id,
        deep_link: `waike://assignment/${a.assignment_id}`,
      });
    }
    if (a.submission_state === "revision_requested" || a.grade_state === "revision_requested") {
      out.push({
        id: `revision:${a.assignment_id}`,
        kind: "revision_requested",
        title: a.title,
        course_title: a.course_title,
        section_id: a.section_id,
        deep_link: `waike://assignment/${a.assignment_id}`,
      });
    }
  }
  for (const row of args.lowMastery || []) {
    out.push({
      id: `mastery:${row.id}`,
      kind: "low_mastery",
      title: row.title,
      course_title: row.course_title,
      section_id: row.section_id,
      deep_link: `waike://study/${row.id}`,
    });
  }
  for (const row of args.syncConflicts || []) {
    out.push({
      id: `sync:${row.id}`,
      kind: "sync_conflict",
      title: row.title,
      course_title: row.course_title,
      section_id: row.section_id,
      deep_link: "waike://home",
    });
  }
  for (const row of args.unacknowledged || []) {
    out.push({
      id: `ack:${row.id}`,
      kind: "unacknowledged",
      title: row.title,
      course_title: row.course_title,
      section_id: row.section_id,
      deep_link: `waike://assignment/${row.id}`,
    });
  }
  return out;
}

export function buildTodayState(args: {
  courses: CourseCardModel[];
  assignments: AssignmentCardModel[];
  calendar: CalendarItem[];
  feedback: FeedbackItem[];
  active: CourseCardModel | null;
  continueItem: TodayContinue | null;
  nowIso: string;
  syncConflicts?: Array<{ id: string; title: string; section_id: string; course_title: string }>;
  lowMastery?: Array<{ id: string; title: string; section_id: string; course_title: string }>;
}): TodayState {
  const due = sortDueSoon(args.assignments, args.nowIso).slice(0, 8);
  return {
    continue_learning: args.continueItem,
    due_soon: due.map((a) => ({
      assignment_id: a.assignment_id,
      section_id: a.section_id,
      course_title: a.course_title,
      title: a.title,
      due_at: a.due_at as string,
      status: a.submission_state,
    })),
    needs_attention: buildNeedsAttention({
      assignments: args.assignments,
      nowIso: args.nowIso,
      syncConflicts: args.syncConflicts,
      lowMastery: args.lowMastery,
    }),
    recent_feedback: [...args.feedback].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 6),
    upcoming: args.calendar
      .filter((c) => !c.overdue && Date.parse(c.at) >= Date.parse(args.nowIso))
      .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
      .slice(0, 8)
      .map((c) => ({
        id: c.id,
        title: c.title,
        at: c.at,
        kind: c.kind,
        section_id: c.section_id,
        deep_link: c.deep_link,
      })),
    courses: args.courses,
    ask_context: {
      section_id: args.active?.section_id ?? null,
      title: args.active?.title ?? null,
    },
  };
}
