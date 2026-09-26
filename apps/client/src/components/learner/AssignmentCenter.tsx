import { useState } from "react";
import { filterAssignments } from "../../lib/product/assignmentCenter";
import type { AssignmentCardModel, AssignmentFilter } from "../../lib/product/types";

const FILTERS: Array<{ id: AssignmentFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "due_soon", label: "Due soon" },
  { id: "submitted", label: "Submitted" },
  { id: "returned", label: "Returned" },
  { id: "missing_overdue", label: "Missing / Overdue" },
  { id: "completed", label: "Completed" },
];

type Props = {
  assignments: AssignmentCardModel[];
  nowIso: string;
  onOpen: (assignmentId: string, sectionId: string) => void;
};

export function AssignmentCenter({ assignments, nowIso, onOpen }: Props) {
  const [filter, setFilter] = useState<AssignmentFilter>("all");
  const rows = filterAssignments(assignments, filter, nowIso);
  return (
    <section className="panel" data-testid="assignment-center">
      <h2>Assignments</h2>
      <div className="mode-bar" role="tablist" aria-label="Assignment filters">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={filter === f.id ? "mode-active" : "ghost"}
            data-testid={`assignment-filter-${f.id}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="muted">No assignments in this filter.</p>
      ) : (
        <ul data-testid="assignment-list">
          {rows.map((a) => (
            <li key={a.assignment_id}>
              <button
                type="button"
                className="ghost"
                data-testid={`open-assignment-${a.assignment_id}`}
                onClick={() => onOpen(a.assignment_id, a.section_id)}
              >
                {a.course_title} · {a.title} · due {a.due_at || "not set"} · {a.submission_state}
                {a.points_possible != null ? ` · ${a.points_possible} pts` : ""}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
