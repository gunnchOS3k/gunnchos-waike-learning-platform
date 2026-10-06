export type LearnerDest =
  | "home"
  | "courses"
  | "assignments"
  | "calendar"
  | "grades"
  | "study"
  | "messages"
  | "portfolio"
  | "more";

export const LEARNER_PRIMARY: Array<{ id: LearnerDest; label: string }> = [
  { id: "home", label: "Home" },
  { id: "courses", label: "Courses" },
  { id: "assignments", label: "Assignments" },
  { id: "calendar", label: "Calendar" },
  { id: "grades", label: "Grades" },
];

export const LEARNER_MORE: Array<{ id: LearnerDest; label: string }> = [
  { id: "study", label: "Study" },
  { id: "messages", label: "Messages" },
  { id: "portfolio", label: "Portfolio" },
];

export const MOBILE_PRIMARY: LearnerDest[] = ["home", "courses", "assignments", "calendar"];
export const MOBILE_MORE = [
  ...LEARNER_PRIMARY.filter((item) => !MOBILE_PRIMARY.includes(item.id)),
  ...LEARNER_MORE,
];

export function isLearnerDest(value: string): value is LearnerDest {
  return [...LEARNER_PRIMARY, ...LEARNER_MORE, { id: "more" as const, label: "More" }].some((x) => x.id === value);
}
