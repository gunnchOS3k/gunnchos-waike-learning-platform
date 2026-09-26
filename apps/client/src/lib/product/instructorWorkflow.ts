export interface DueShiftItem {
  id: string;
  title: string;
  current_due: string | null;
  proposed_due: string | null;
}

export interface DueShiftPreview {
  section_id: string;
  delta_hours: number;
  items: DueShiftItem[];
}

export function previewDueDateShift(
  items: Array<{ id: string; title: string; current_due: string | null }>,
  deltaHours: number,
): DueShiftItem[] {
  return items.map((item) => ({
    id: item.id,
    title: item.title,
    current_due: item.current_due,
    proposed_due: item.current_due
      ? new Date(Date.parse(item.current_due) + deltaHours * 3600_000).toISOString()
      : null,
  }));
}

export type InterventionSignal = "missing_work" | "low_mastery" | "revision_requested" | "inactivity";

export interface InterventionRow {
  learner_id: string;
  display_name: string;
  signals: InterventionSignal[];
  waiting_for_instructor_grade: boolean;
  deep_link: string;
}

export function classifyIntervention(args: {
  learner_id: string;
  display_name: string;
  missingWork: boolean;
  lowMastery: boolean;
  revisionRequested: boolean;
  inactivityTrusted: boolean;
  waitingForInstructorGrade: boolean;
}): InterventionRow | null {
  const signals: InterventionSignal[] = [];
  if (args.missingWork) signals.push("missing_work");
  if (args.lowMastery) signals.push("low_mastery");
  if (args.revisionRequested) signals.push("revision_requested");
  if (args.inactivityTrusted) signals.push("inactivity");
  if (signals.length === 0) return null;
  return {
    learner_id: args.learner_id,
    display_name: args.display_name,
    signals,
    waiting_for_instructor_grade: args.waitingForInstructorGrade,
    deep_link: `waike://course/${args.learner_id}`,
  };
}

export function filterIntervention(
  rows: InterventionRow[],
  signal: InterventionSignal | "all",
): InterventionRow[] {
  return rows.filter((row) => {
    if (row.waiting_for_instructor_grade && row.signals.length === 0) return false;
    if (signal === "all") return row.signals.length > 0;
    return row.signals.includes(signal);
  });
}
