import { gradeRowHonesty, overallPercentAllowed } from "../../lib/product/gradesHonesty";
import type { LearnerGradeRow } from "../../lib/product/types";

type Props = {
  rows: LearnerGradeRow[];
  weightingModeled: boolean;
  overallPercent?: number | null;
  onOpen: (assignmentId: string) => void;
  onMastery?: (assignmentId: string) => void;
};

export function LearnerGrades({ rows, weightingModeled, overallPercent, onOpen, onMastery }: Props) {
  const overall = overallPercentAllowed({ weightingModeled, overallPercent: overallPercent ?? null });
  return (
    <section className="panel" data-testid="learner-grades">
      <h2>Grades</h2>
      {overall == null ? (
        <p className="muted" data-testid="no-overall-percent">
          No overall course percentage is shown because weighting is not fully modeled.
        </p>
      ) : (
        <p data-testid="overall-percent">Course total {overall.toFixed(1)}%</p>
      )}
      {rows.length === 0 ? (
        <p className="muted">No graded or pending work yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Work</th>
              <th scope="col">Score</th>
              <th scope="col">Status</th>
              <th scope="col">Feedback</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const honesty = gradeRowHonesty(row.status, row.points_earned);
              return (
                <tr key={row.assignment_id}>
                  <td>
                    <button type="button" className="ghost" onClick={() => onOpen(row.assignment_id)}>
                      {row.course_title} · {row.title}
                    </button>
                  </td>
                  <td>
                    {row.points_earned == null
                      ? "—"
                      : `${row.points_earned}/${row.points_possible ?? "—"}`}
                  </td>
                  <td>{honesty.label}</td>
                  <td>
                    {row.feedback || "—"}
                    {onMastery ? (
                      <button type="button" className="ghost" onClick={() => onMastery(row.assignment_id)}>
                        Mastery
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
