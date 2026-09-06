import { useCallback, useEffect, useState } from "react";

export type AiPolicyName =
  | "AI_ALLOWED"
  | "AI_HINTS_ONLY"
  | "AI_DISABLED"
  | "AI_INSTRUCTOR_DEFINED";

export interface EffectiveAiPolicy {
  policy: AiPolicyName;
  scope: string;
  section_id: string;
  allowed_learner_capabilities: string[];
  allowed_instructor_capabilities: string[];
}

export interface AiAssistResult {
  ok: boolean;
  text: string;
  grounded: boolean;
  citations: Array<{ source?: string; snippet?: string }>;
  refused: boolean;
  refusal_code: string | null;
  disclosure: string;
  suggestion_only: boolean;
  mutates_grades: boolean;
  policy?: string;
  provider_id?: string;
}

export interface AiClient {
  getPolicy(sectionId: string, assessmentId?: string, activityId?: string): Promise<EffectiveAiPolicy>;
  learnerAssist(body: {
    section_id: string;
    capability: string;
    query: string;
    assessment_id?: string;
    activity_id?: string;
    course_materials?: Array<{ id?: string; path?: string; text?: string }>;
  }): Promise<AiAssistResult>;
  instructorAssist(body: {
    section_id: string;
    capability: string;
    query: string;
    assessment_id?: string;
    activity_id?: string;
  }): Promise<AiAssistResult>;
  /** Always refused by the server — exposed so UI never auto-applies grades. */
  applyGrade(body: {
    section_id?: string;
    submission_id?: string;
    points?: number;
    explicit_confirm?: boolean;
  }): Promise<never>;
}

export function createAiClient(req: <T>(path: string, init?: RequestInit) => Promise<T>): AiClient {
  return {
    getPolicy: (sectionId, assessmentId, activityId) => {
      const q = new URLSearchParams({ section_id: sectionId });
      if (assessmentId) q.set("assessment_id", assessmentId);
      if (activityId) q.set("activity_id", activityId);
      return req(`/api/v1/ai/policy?${q.toString()}`);
    },
    learnerAssist: (body) =>
      req("/api/v1/ai/learner/assist", { method: "POST", body: JSON.stringify(body) }),
    instructorAssist: (body) =>
      req("/api/v1/ai/instructor/assist", { method: "POST", body: JSON.stringify(body) }),
    applyGrade: (body) =>
      req("/api/v1/ai/instructor/apply-grade", { method: "POST", body: JSON.stringify(body) }),
  };
}

function errText(err: unknown): string {
  if (err instanceof Error) return err.message.replace(/^\d+:/, "");
  return String(err);
}

const LEARNER_ACTIONS: Array<{ capability: string; label: string }> = [
  { capability: "explain", label: "Explain" },
  { capability: "hint", label: "Hint" },
  { capability: "misconception", label: "Diagnose misconception" },
  { capability: "remediation", label: "Remediation" },
  { capability: "citation", label: "Cite materials" },
  { capability: "navigate", label: "Navigate" },
  { capability: "lab_troubleshoot", label: "Lab help" },
  { capability: "reflect", label: "Reflect" },
];

/**
 * Learner AI panel — respects server policy; never requests answer keys.
 */
export function LearnerAiPanel({
  ai,
  sectionId,
}: {
  ai: AiClient;
  sectionId: string;
}) {
  const [policy, setPolicy] = useState<EffectiveAiPolicy | null>(null);
  const [capability, setCapability] = useState("hint");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AiAssistResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    ai.getPolicy(sectionId)
      .then((p) => {
        if (!alive) return;
        setPolicy(p);
        const allowed = p.allowed_learner_capabilities;
        setCapability((prev) => (allowed.length && !allowed.includes(prev) ? allowed[0] : prev));
      })
      .catch((e) => alive && setError(errText(e)));
    return () => {
      alive = false;
    };
  }, [ai, sectionId]);

  const ask = useCallback(async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await ai.learnerAssist({
        section_id: sectionId,
        capability,
        query,
        course_materials: [
          {
            id: "section-lesson",
            path: "learner/lessons/current",
            text: "Course materials for this section (learner pack only).",
          },
        ],
      });
      setResult(r);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [ai, sectionId, capability, query]);

  const disabled = policy?.policy === "AI_DISABLED";
  const allowed = new Set(policy?.allowed_learner_capabilities ?? []);

  return (
    <section className="panel ai-panel" data-testid="learner-ai-panel" aria-labelledby="learner-ai-heading">
      <h2 id="learner-ai-heading">gunnchAI tutor</h2>
      {policy ? (
        <p className="muted" data-testid="learner-ai-policy">
          Policy: <strong>{policy.policy}</strong> ({policy.scope})
        </p>
      ) : (
        <p className="muted">Loading policy…</p>
      )}
      {disabled ? (
        <p role="status" data-testid="learner-ai-disabled">
          AI is disabled for this section. Ask your instructor if you need help.
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <label className="field-label" htmlFor="learner-ai-capability">
            Help type
          </label>
          <select
            id="learner-ai-capability"
            data-testid="learner-ai-capability"
            value={capability}
            onChange={(e) => setCapability(e.target.value)}
            disabled={busy}
          >
            {LEARNER_ACTIONS.filter((a) => allowed.size === 0 || allowed.has(a.capability)).map(
              (a) => (
                <option key={a.capability} value={a.capability}>
                  {a.label}
                </option>
              ),
            )}
          </select>
          <label className="field-label" htmlFor="learner-ai-query">
            Your question
          </label>
          <textarea
            id="learner-ai-query"
            data-testid="learner-ai-query"
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
            disabled={busy}
            aria-describedby="learner-ai-hint"
          />
          <p id="learner-ai-hint" className="muted">
            Answers are grounded in course materials. Answer keys are never revealed.
          </p>
          <button type="submit" data-testid="learner-ai-ask" disabled={busy || !query.trim()}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </form>
      )}
      {error ? (
        <p className="activity-error" role="alert" data-testid="learner-ai-error">
          {error}
        </p>
      ) : null}
      {result ? (
        <div className="ai-result" data-testid="learner-ai-result" role="status">
          {result.refused ? (
            <p role="alert">{result.text}</p>
          ) : (
            <>
              <p>{result.text}</p>
              {result.citations.length > 0 ? (
                <ul aria-label="Citations">
                  {result.citations.map((c, i) => (
                    <li key={i}>
                      {c.source}: {c.snippet}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
          <p className="muted">{result.disclosure}</p>
        </div>
      ) : null}
    </section>
  );
}

const INSTRUCTOR_ACTIONS: Array<{ capability: string; label: string }> = [
  { capability: "feedback_suggest", label: "Feedback suggestion" },
  { capability: "rubric_refine", label: "Rubric refinement" },
  { capability: "misconception_cluster", label: "Misconception clustering" },
  { capability: "remediation_suggest", label: "Remediation" },
  { capability: "lesson_adapt", label: "Lesson adaptation" },
  { capability: "grading_triage", label: "Grading triage" },
];

/**
 * Instructor AI suggestions — cannot auto-apply grades.
 */
export function InstructorAiPanel({
  ai,
  sectionId,
}: {
  ai: AiClient;
  sectionId: string;
}) {
  const [capability, setCapability] = useState("feedback_suggest");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AiAssistResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyMsg, setApplyMsg] = useState<string | null>(null);

  const ask = useCallback(async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    setApplyMsg(null);
    try {
      const r = await ai.instructorAssist({
        section_id: sectionId,
        capability,
        query,
      });
      setResult(r);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [ai, sectionId, capability, query]);

  const tryApplyGrade = useCallback(async () => {
    setApplyMsg(null);
    try {
      await ai.applyGrade({
        section_id: sectionId,
        submission_id: "sub_demo",
        points: 100,
        explicit_confirm: true,
      });
      setApplyMsg("Unexpected success — grades must never auto-apply.");
    } catch (e) {
      setApplyMsg(`Blocked (expected): ${errText(e)}`);
    }
  }, [ai, sectionId]);

  return (
    <section
      className="panel ai-panel"
      data-testid="instructor-ai-panel"
      aria-labelledby="instructor-ai-heading"
    >
      <h2 id="instructor-ai-heading">gunnchAI instructor suggestions</h2>
      <p className="muted">
        Suggestions only. Grades and feedback are applied through normal grading actions — never
        silently by AI.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
      >
        <label className="field-label" htmlFor="instructor-ai-capability">
          Suggestion type
        </label>
        <select
          id="instructor-ai-capability"
          data-testid="instructor-ai-capability"
          value={capability}
          onChange={(e) => setCapability(e.target.value)}
          disabled={busy}
        >
          {INSTRUCTOR_ACTIONS.map((a) => (
            <option key={a.capability} value={a.capability}>
              {a.label}
            </option>
          ))}
        </select>
        <label className="field-label" htmlFor="instructor-ai-query">
          Context / request
        </label>
        <textarea
          id="instructor-ai-query"
          data-testid="instructor-ai-query"
          rows={3}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          required
          disabled={busy}
        />
        <div className="toolbar">
          <button type="submit" data-testid="instructor-ai-ask" disabled={busy || !query.trim()}>
            {busy ? "Drafting…" : "Get suggestion"}
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="instructor-ai-apply-blocked"
            onClick={() => void tryApplyGrade()}
          >
            Try auto-apply grade (blocked)
          </button>
        </div>
      </form>
      {error ? (
        <p className="activity-error" role="alert" data-testid="instructor-ai-error">
          {error}
        </p>
      ) : null}
      {applyMsg ? (
        <p role="status" data-testid="instructor-ai-apply-msg">
          {applyMsg}
        </p>
      ) : null}
      {result ? (
        <div className="ai-result" data-testid="instructor-ai-result" role="status">
          <p>{result.text}</p>
          <p className="muted">
            suggestion_only={String(result.suggestion_only)} · mutates_grades=
            {String(result.mutates_grades)}
          </p>
        </div>
      ) : null}
    </section>
  );
}
