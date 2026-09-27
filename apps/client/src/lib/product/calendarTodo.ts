import type { CalendarItem } from "./types";
import { isOverdue } from "./todayHome";

export type CalendarBucket = "today" | "this_week" | "later" | "overdue";

export function bucketCalendarItem(item: CalendarItem, nowIso: string, timeZone = "UTC"): CalendarBucket {
  if (item.overdue || isOverdue(item.at, nowIso, item.overdue)) return "overdue";
  const now = new Date(nowIso);
  const at = new Date(item.at);
  const todayKey = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const atKey = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(at);
  if (atKey === todayKey) return "today";
  const weekFromNow = new Date(Date.parse(nowIso) + 7 * 24 * 60 * 60 * 1000);
  if (at.getTime() <= weekFromNow.getTime()) return "this_week";
  return "later";
}

export function groupCalendar(items: CalendarItem[], nowIso: string, timeZone = "UTC"): Record<CalendarBucket, CalendarItem[]> {
  const groups: Record<CalendarBucket, CalendarItem[]> = {
    overdue: [],
    today: [],
    this_week: [],
    later: [],
  };
  const sorted = [...items].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  for (const item of sorted) {
    groups[bucketCalendarItem(item, nowIso, timeZone)].push(item);
  }
  return groups;
}

export function calendarFromAssignments(
  rows: Array<{
    assignment_id: string;
    title: string;
    due_at: string | null;
    section_id: string;
    course_title: string;
    kind?: CalendarItem["kind"];
  }>,
  nowIso: string,
  authoritativeOverdueIds: string[] = [],
): CalendarItem[] {
  return rows
    .filter((row) => Boolean(row.due_at))
    .map((row) => ({
      id: row.assignment_id,
      title: row.title,
      at: row.due_at as string,
      kind: row.kind ?? "assignment",
      section_id: row.section_id,
      course_title: row.course_title,
      deep_link: `waike://assignment/${row.assignment_id}`,
      overdue: authoritativeOverdueIds.includes(row.assignment_id) || isOverdue(row.due_at, nowIso),
    }));
}
