import { useState } from "react";
import type { AssignmentDetail, HubClient, SubmissionView } from "../../lib/hub/client";
import type { CommentSnippet } from "./InstructorWave1";

type Props = {
  hub: HubClient;
  assignment: AssignmentDetail | null;
  queue: Array<{ submission_id: string; learner_id: string; attempt_number: number; status: string }>;
  comments: CommentSnippet[];
  anonymous?: boolean;
  onReload: () => Promise<void>;
};

export function GradingWorkspace({ hub, assignment, queue, comments, anonymous = false, onReload }: Props) {
  const [active, setActive] = useState<SubmissionView | null>(null);
  const [feedback, setFeedback] = useState("");
  const [points, setPoints] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const next = queue.find((q) => q.status === "submitted" || !["returned", "graded"].includes(q.status));

  async function open(id: string) {
    setError(null);
    setActive(await hub.getSubmission(id));
  }

  async function onGrade() {
    if (!active || !assignment) return;
    try {
      const result = await hub.grade(active.submission_id, {
        criterion_scores: assignment.rubric.criteria.map((c) => ({
          criterion_id: c.criterion_id,
          points: points[c.criterion_id] ?? 2,
          comment: `score ${points[c.criterion_id] ?? 2}`,
        })),
        feedback_body: feedback,
      });
      setMessage(`Saved · mastery=${result.mastery.mastered}`);
      await onReload();
      const nxt = queue.find((q) => q.submission_id !== active.submission_id);
      if (nxt) await open(nxt.submission_id);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <section className="panel" data-testid="grading-workspace">
      <h2>Grading</h2>
      <p className="muted">{assignment?.title || "Select work from the queue."}</p>
      {next ? (
        <button type="button" className="ghost" data-testid="next-ungraded" onClick={() => void open(next.submission_id)}>
          Next ungraded
        </button>
      ) : (
        <p className="muted">Queue is clear.</p>
      )}
      <ul>
        {queue.map((q) => (
          <li key={q.submission_id}>
            <button type="button" className="ghost" onClick={() => void open(q.submission_id)}>
              {anonymous ? `Submission ${q.attempt_number}` : `${q.learner_id} · attempt ${q.attempt_number}`} · {q.status}
            </button>
          </li>
        ))}
      </ul>
      {active ? (
        <div>
          <p>Attempt {active.attempt_number}</p>
          <p>{active.text_response}</p>
          {assignment ? (
            <div data-testid="criterion-scores">
              {assignment.rubric.criteria.map((c) => (
                <label key={c.criterion_id} className="field-label">
                  {c.description}
                  <input
                    type="number"
                    value={points[c.criterion_id] ?? 2}
                    onChange={(e) => setPoints((p) => ({ ...p, [c.criterion_id]: Number(e.target.value) }))}
                  />
                </label>
              ))}
            </div>
          ) : null}
          <label className="field-label" htmlFor="grade-feedback">
            Feedback
          </label>
          <textarea id="grade-feedback" rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
          <div className="toolbar">
            {comments.map((c) => (
              <button key={c.comment_id} type="button" className="ghost" onClick={() => setFeedback(c.body)}>
                {c.title}
              </button>
            ))}
          </div>
          <button type="button" data-testid="save-next-grade" onClick={() => void onGrade()}>
            Save and next
          </button>
        </div>
      ) : null}
      {message ? <p data-testid="grading-status">{message}</p> : null}
      {error ? <div className="error-box">{error}</div> : null}
    </section>
  );
}
