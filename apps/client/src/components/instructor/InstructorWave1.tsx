import { useMemo, useState } from "react";
import { filterIntervention, previewDueDateShift, type InterventionRow } from "../../lib/product/instructorWorkflow";

export interface CommentSnippet {
  comment_id: string;
  title: string;
  body: string;
}

type Props = {
  sections: Array<{ section_id: string; title: string; package_id?: string }>;
  dueItems: Array<{ id: string; title: string; current_due: string | null }>;
  comments: CommentSnippet[];
  intervention: InterventionRow[];
  onCopy: (body: { source_section_id: string; code: string; title: string; term: string }) => void;
  onApplyShift: (deltaHours: number) => void;
  onSaveComment: (title: string, body: string) => void;
  onMessage: (learnerId: string) => void;
};

export function InstructorWave1({
  sections,
  dueItems,
  comments,
  intervention,
  onCopy,
  onApplyShift,
  onSaveComment,
  onMessage,
}: Props) {
  const [source, setSource] = useState(sections[0]?.section_id || "");
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [term, setTerm] = useState("");
  const [hours, setHours] = useState(24);
  const [cTitle, setCTitle] = useState("");
  const [cBody, setCBody] = useState("");
  const [signal, setSignal] = useState<"all" | "missing_work" | "low_mastery" | "revision_requested" | "inactivity">("all");
  const preview = useMemo(() => previewDueDateShift(dueItems, hours), [dueItems, hours]);
  const rows = filterIntervention(intervention, signal);

  return (
    <section className="panel" data-testid="instructor-wave1">
      <h2>Course setup</h2>
      <p className="muted">Copy creates a new section that still points at the same course package. Curriculum source is not duplicated.</p>
      <label className="field-label" htmlFor="copy-source">
        Template course
      </label>
      <select id="copy-source" data-testid="copy-source" value={source} onChange={(e) => setSource(e.target.value)}>
        {sections.map((s) => (
          <option key={s.section_id} value={s.section_id}>
            {s.title}
          </option>
        ))}
      </select>
      <label className="field-label" htmlFor="copy-code">
        New section code
      </label>
      <input id="copy-code" data-testid="copy-code" value={code} onChange={(e) => setCode(e.target.value)} />
      <label className="field-label" htmlFor="copy-title">
        New section title
      </label>
      <input id="copy-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <label className="field-label" htmlFor="copy-term">
        Term
      </label>
      <input id="copy-term" value={term} onChange={(e) => setTerm(e.target.value)} />
      <button
        type="button"
        data-testid="copy-section"
        onClick={() => onCopy({ source_section_id: source, code, title, term })}
      >
        Create section from template
      </button>

      <h3>Due-date shift</h3>
      <label className="field-label" htmlFor="shift-hours">
        Hours to shift
      </label>
      <input
        id="shift-hours"
        type="number"
        data-testid="shift-hours"
        value={hours}
        onChange={(e) => setHours(Number(e.target.value))}
      />
      <ul data-testid="shift-preview">
        {preview.map((item) => (
          <li key={item.id}>
            {item.title}: {item.current_due || "none"} → {item.proposed_due || "unchanged"}
          </li>
        ))}
      </ul>
      <button type="button" data-testid="shift-apply" onClick={() => onApplyShift(hours)}>
        Apply shift
      </button>

      <h3>Comment bank</h3>
      <ul data-testid="comment-bank">
        {comments.map((c) => (
          <li key={c.comment_id}>
            <strong>{c.title}</strong> — {c.body}
          </li>
        ))}
      </ul>
      <input placeholder="Snippet title" value={cTitle} onChange={(e) => setCTitle(e.target.value)} />
      <textarea placeholder="Reusable comment" value={cBody} onChange={(e) => setCBody(e.target.value)} rows={3} />
      <button type="button" data-testid="save-comment" onClick={() => onSaveComment(cTitle, cBody)}>
        Save comment
      </button>

      <h3>Needs a check-in</h3>
      <p className="muted">Waiting for you to grade is not treated as a learner problem.</p>
      <select data-testid="intervention-filter" value={signal} onChange={(e) => setSignal(e.target.value as typeof signal)}>
        <option value="all">All signals</option>
        <option value="missing_work">Missing work</option>
        <option value="low_mastery">Low mastery</option>
        <option value="revision_requested">Requested revision</option>
        <option value="inactivity">Inactivity (trusted only)</option>
      </select>
      <ul data-testid="intervention-list">
        {rows.map((r) => (
          <li key={r.learner_id}>
            {r.display_name} · {r.signals.join(", ")}
            <button type="button" className="ghost" onClick={() => onMessage(r.learner_id)}>
              Message
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
