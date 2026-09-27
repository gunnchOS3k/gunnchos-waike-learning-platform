import type { AssignmentCardModel, AssignmentFilter } from "./types";
import { isOverdue } from "./todayHome";

const SOON_MS = 7 * 24 * 60 * 60 * 1000;

export function classifyAssignment(item: AssignmentCardModel, nowIso: string): AssignmentFilter[] {
  const keys: AssignmentFilter[] = ["all"];
  const overdue = isOverdue(item.due_at, nowIso);
  const dueSoon =
    Boolean(item.due_at) &&
    !overdue &&
    Date.parse(item.due_at as string) - Date.parse(nowIso) <= SOON_MS;
  if (dueSoon) keys.push("due_soon");
  if (item.submission_state === "submitted") keys.push("submitted");
  if (item.submission_state === "returned" || item.grade_state === "returned") keys.push("returned");
  if (overdue && item.submission_state !== "submitted" && item.submission_state !== "returned") {
    keys.push("missing_overdue");
  }
  if (item.submission_state === "complete" || item.grade_state === "complete") keys.push("completed");
  return keys;
}

export function filterAssignments(
  items: AssignmentCardModel[],
  filter: AssignmentFilter,
  nowIso: string,
): AssignmentCardModel[] {
  return items.filter((item) => classifyAssignment(item, nowIso).includes(filter));
}

export function pickOpenAssignment(
  items: AssignmentCardModel[],
  requestedId: string | null,
): AssignmentCardModel | null {
  if (!requestedId) return null;
  return items.find((item) => item.assignment_id === requestedId) ?? null;
}
