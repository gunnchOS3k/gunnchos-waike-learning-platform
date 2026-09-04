import { useCallback, useEffect, useState } from "react";
import type { AssignmentDetail, DraftState, HubClient, SubmissionView } from "../../lib/hub/client";

type Props = {
  hub: HubClient;
};

export function AssessmentWorkspace({ hub }: Props) {
  const [assignment, setAssignment] = useState<AssignmentDetail | null>(null);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [text, setText] = useState("");
  const [artifactName, setArtifactName] = useState<string | null>(null);
  const [submission, setSubmission] = useState<SubmissionView | null>(null);
  const [history, setHistory] = useState<Array<{ submission_id: string; attempt_number: number; status: string }>>([]);
  const [remediation, setRemediation] = useState<Array<{ plan_id: string; task_markdown: string; status: string }>>([]);
  const [portfolio, setPortfolio] = useState<Array<{ title: string; evidence_hash: string }>>([]);
  const [mastery, setMastery] = useState<{ mastered?: number; gap_notes?: string }>({});
  const [gradebook, setGradebook] = useState<Array<{ points_earned: number; points_possible: number; status: string }>>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveTimer, setSaveTimer] = useState<number | null>(null);

  const refreshSide = useCallback(async () => {
    if (!assignment) return;
    const [h, r, p, m, g] = await Promise.all([
      hub.history(assignment.assignment_id),
      hub.remediation(),
      hub.portfolio(),
      hub.mastery(assignment.assignment_id),
      hub.gradebook(),
    ]);
    setHistory(h);
    setRemediation(r.filter((x: { assignment_id: string }) => x.assignment_id === assignment.assignment_id));
    setPortfolio(p);
    setMastery(m);
    setGradebook(g.filter((x: { assignment_id: string }) => x.assignment_id === assignment.assignment_id));
  }, [assignment, hub]);

  useEffect(() => {
    (async () => {
      try {
        const list = await hub.listAssignments();
        const id = list[0]?.assignment_id;
        if (!id) return;
        const detail = await hub.getAssignment(id);
        setAssignment(detail);
        const d = await hub.getDraft(id);
        setDraft(d);
        setText(d.text_response || "");
        setArtifactName(d.artifact_name);
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [hub]);

  useEffect(() => {
    void refreshSide();
  }, [refreshSide, submission]);

  function scheduleAutosave(next: string) {
    setText(next);
    if (saveTimer) window.clearTimeout(saveTimer);
    const t = window.setTimeout(() => {
      void (async () => {
        if (!assignment) return;
        try {
          const saved = await hub.saveDraft(assignment.assignment_id, next, artifactName || undefined);
          setDraft(saved);
          setStatus(`Draft autosaved (rev ${saved.revision})`);
        } catch (e) {
          setError(String(e));
        }
      })();
    }, 400);
    setSaveTimer(t);
  }

  async function onAttach(file: File | null) {
    if (!file || !assignment) return;
    const buf = await file.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    const saved = await hub.saveDraft(assignment.assignment_id, text, file.name, b64);
    setDraft(saved);
    setArtifactName(file.name);
    setStatus(`Attached ${file.name}`);
  }

  async function onSubmit() {
    if (!assignment) return;
    setError(null);
    try {
      const key = `ui-${assignment.assignment_id}-${history.length + 1}`;
      const sub = await hub.submit(assignment.assignment_id, key, text);
      setSubmission(sub);
      setStatus(`Submitted — receipt ${sub.receipt?.receipt_id}`);
      await refreshSide();
    } catch (e) {
      setError(String(e));
    }
  }

  async function openHistory(id: string) {
    try {
      const sub = await hub.getSubmission(id);
      setSubmission(sub);
    } catch (e) {
      setError(String(e));
    }
  }

  if (!assignment) {
    return (
      <section className="panel" data-testid="assignment-workspace">
        <h2>Assignments</h2>
        <p className="muted">Loading DIGITAL_CONFIDENCE assignments…</p>
      </section>
    );
  }

  return (
    <section className="panel" data-testid="assignment-workspace">
      <h2>{assignment.title}</h2>
      <p className="muted">
        {assignment.module_id} · week {assignment.week} · source {assignment.source_path}
      </p>
      <article className="assignment-body" data-testid="assignment-body">
        <pre>{assignment.body_markdown.slice(0, 1200)}{assignment.body_markdown.length > 1200 ? "…" : ""}</pre>
      </article>

      <label className="field-label" htmlFor="draft-text">
        Your response
      </label>
      <textarea
        id="draft-text"
        data-testid="draft-text"
        rows={8}
        value={text}
        onChange={(e) => scheduleAutosave(e.target.value)}
        placeholder="Write your reflection…"
      />
      <div className="toolbar">
        <label className="ghost file-btn">
          Attach artifact
          <input
            data-testid="artifact-input"
            type="file"
            hidden
            onChange={(e) => void onAttach(e.target.files?.[0] || null)}
          />
        </label>
        <button type="button" data-testid="submit-btn" onClick={() => void onSubmit()}>
          Submit
        </button>
      </div>
      {artifactName ? <p className="muted">Attachment: {artifactName}</p> : null}
      {draft?.updated_at ? (
        <p className="muted" data-testid="draft-meta">
          Draft rev {draft.revision} · {draft.updated_at}
        </p>
      ) : null}

      {status ? <p data-testid="assignment-status">{status}</p> : null}
      {error ? (
        <div className="error-box" role="alert">
          {error}
        </div>
      ) : null}

      {submission ? (
        <div className="receipt-card" data-testid="receipt-card">
          <h3>Submission receipt</h3>
          <p>
            {submission.submission_id} · attempt {submission.attempt_number} · hash{" "}
            <code>{submission.content_hash.slice(0, 12)}…</code>
          </p>
          {submission.grade ? (
            <p data-testid="learner-grade">
              Grade {submission.grade.points_earned}/{submission.grade.points_possible}
            </p>
          ) : null}
          {submission.feedback.map((f) => (
            <p key={f.feedback_id} data-testid="learner-feedback">
              Feedback: {f.body}
            </p>
          ))}
        </div>
      ) : null}

      <div className="side-grid">
        <div>
          <h3>History</h3>
          <ul data-testid="submission-history">
            {history.map((h) => (
              <li key={h.submission_id}>
                <button type="button" className="ghost" onClick={() => void openHistory(h.submission_id)}>
                  Attempt {h.attempt_number} · {h.status}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3>Remediation</h3>
          <ul data-testid="remediation-list">
            {remediation.map((r) => (
              <li key={r.plan_id}>
                [{r.status}] {r.task_markdown}
              </li>
            ))}
          </ul>
          <h3>Mastery</h3>
          <p data-testid="mastery-state">
            {mastery.mastered === 1 ? "Mastered" : mastery.mastered === 0 ? `Gap: ${mastery.gap_notes || "yes"}` : "Not evaluated"}
          </p>
          <h3>Gradebook</h3>
          <ul data-testid="gradebook-list">
            {gradebook.map((g, i) => (
              <li key={i}>
                {g.points_earned}/{g.points_possible} · {g.status}
              </li>
            ))}
          </ul>
          <h3>Portfolio</h3>
          <ul data-testid="portfolio-list">
            {portfolio.map((p, i) => (
              <li key={i}>
                {p.title} · <code>{p.evidence_hash.slice(0, 10)}…</code>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
