import { useEffect, useState } from "react";
import type { AssignmentDetail, HubClient, SubmissionView } from "../../lib/hub/client";

type Props = { hub: HubClient };

export function InstructorQueue({ hub }: Props) {
  const [assignment, setAssignment] = useState<AssignmentDetail | null>(null);
  const [queue, setQueue] = useState<Array<{ submission_id: string; learner_id: string; attempt_number: number; status: string }>>([]);
  const [active, setActive] = useState<SubmissionView | null>(null);
  const [feedback, setFeedback] = useState("Instructor feedback");
  const [criterionPoints, setCriterionPoints] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    const list = await hub.listAssignments();
    const id = list[0]?.assignment_id;
    if (!id) return;
    const detail = await hub.getAssignment(id);
    setAssignment(detail);
    const initial: Record<string, number> = {};
    for (const c of detail.rubric.criteria) {
      initial[c.criterion_id] = 2;
    }
    setCriterionPoints(initial);
    setQueue(await hub.queue(id));
  }

  useEffect(() => {
    void reload().catch((e) => setError(String(e)));
  }, [hub]);

  async function open(id: string) {
    setError(null);
    try {
      setActive(await hub.getSubmission(id));
    } catch (e) {
      setError(String(e));
    }
  }

  async function onGrade() {
    if (!active || !assignment) return;
    setError(null);
    try {
      const result = await hub.grade(active.submission_id, {
        criterion_scores: assignment.rubric.criteria.map((c) => {
          const points = criterionPoints[c.criterion_id] ?? 0;
          return {
            criterion_id: c.criterion_id,
            points,
            level_id: c.levels.find((l) => l.score === points)?.level_id,
            comment: `score ${points}`,
          };
        }),
        feedback_body: feedback,
      });
      setMessage(
        `Graded · mastery=${result.mastery.mastered} · remediation=${result.remediation?.status || "none"} · portfolio=${result.portfolio ? "yes" : "no"}`,
      );
      setActive(await hub.getSubmission(active.submission_id));
      await reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <section className="panel" data-testid="instructor-queue">
      <h2>Instructor grading queue</h2>
      <p className="muted">{assignment ? assignment.title : "Loading…"}</p>
      <ul data-testid="queue-list">
        {queue.map((q) => (
          <li key={q.submission_id}>
            <button type="button" className="ghost" onClick={() => void open(q.submission_id)}>
              {q.learner_id} · attempt {q.attempt_number} · {q.status}
            </button>
          </li>
        ))}
      </ul>

      {active ? (
        <div className="grade-panel" data-testid="grade-panel">
          <h3>Submission {active.submission_id}</h3>
          <pre className="assignment-body">{active.text_response}</pre>
          <fieldset data-testid="criterion-scores">
            <legend>Criterion scores</legend>
            {assignment?.rubric.criteria.map((c) => (
              <div key={c.criterion_id} className="criterion-row">
                <label className="field-label" htmlFor={`crit-${c.criterion_id}`}>
                  {c.description} (0–{c.max_points})
                </label>
                <input
                  id={`crit-${c.criterion_id}`}
                  data-testid={`rubric-points-${c.criterion_id}`}
                  type="number"
                  min={0}
                  max={c.max_points}
                  value={criterionPoints[c.criterion_id] ?? 0}
                  onChange={(e) =>
                    setCriterionPoints((prev) => ({
                      ...prev,
                      [c.criterion_id]: Number(e.target.value),
                    }))
                  }
                />
              </div>
            ))}
          </fieldset>
          {/* Compat alias for older tests */}
          <input
            data-testid="rubric-points"
            type="hidden"
            value={Object.values(criterionPoints)[0] ?? 2}
            readOnly
          />
          <label className="field-label" htmlFor="feedback">
            Feedback
          </label>
          <textarea
            id="feedback"
            data-testid="feedback-text"
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
          <div className="toolbar">
            <button type="button" data-testid="return-grade-btn" onClick={() => void onGrade()}>
              Return grade
            </button>
          </div>
        </div>
      ) : null}

      {message ? <p data-testid="instructor-status">{message}</p> : null}
      {error ? (
        <div className="error-box" role="alert">
          {error}
        </div>
      ) : null}
    </section>
  );
}
