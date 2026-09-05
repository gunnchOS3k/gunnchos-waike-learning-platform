import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ActivityClient,
  GroupView,
  LabRunView,
  LabView,
  LearnerQuizView,
  PostView,
  LearnerAttemptDetail,
  QuizAttemptStart,
  SectionActivities,
  ThreadView,
} from "../../lib/hub/activities";

/**
 * Learner-facing activities. Nothing here can request an answer key: the learner
 * client type has no such method, and the server refuses the route anyway.
 */

/** Client mutation ids must be unique per attempt and at least 8 characters. */
function newMutationId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `mut_${prefix}_${rand}`.replace(/-/g, "").slice(0, 64);
}

function errText(err: unknown): string {
  if (err instanceof Error) return err.message.replace(/^\d+:/, "");
  return String(err);
}

function fmtScore(score: number | null, max: number | null): string {
  if (score == null || max == null) return "Not scored yet";
  return `${score} / ${max}`;
}

/** Advisory countdown. The server owns the real deadline; this only informs. */
function useCountdown(deadlineIso: string | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!deadlineIso) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [deadlineIso]);
  if (!deadlineIso) return null;
  const remaining = Date.parse(deadlineIso) - now;
  if (Number.isNaN(remaining)) return null;
  if (remaining <= 0) return "Time is up — your work is still saved";
  const mins = Math.floor(remaining / 60000);
  const secs = Math.floor((remaining % 60000) / 1000);
  return `${mins}:${String(secs).padStart(2, "0")} remaining (approximate)`;
}

function QuizRunner({
  activities,
  quizId,
  onFinished,
}: {
  activities: ActivityClient;
  quizId: string;
  onFinished: () => void;
}) {
  const [quiz, setQuiz] = useState<LearnerQuizView | null>(null);
  const [attempt, setAttempt] = useState<QuizAttemptStart | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [result, setResult] = useState<LearnerAttemptDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [startedAtMs, setStartedAtMs] = useState<number | null>(null);
  const countdown = useCountdown(attempt?.deadline_at ?? null);

  useEffect(() => {
    let alive = true;
    activities
      .getQuiz(quizId)
      .then((q) => alive && setQuiz(q))
      .catch((e) => alive && setError(errText(e)));
    return () => {
      alive = false;
    };
  }, [activities, quizId]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const a = await activities.startQuizAttempt(quizId);
      setAttempt(a);
      setStartedAtMs(Date.now());
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [activities, quizId]);

  const submit = useCallback(async () => {
    if (!attempt) return;
    setBusy(true);
    setError(null);
    try {
      const elapsed = startedAtMs ? (Date.now() - startedAtMs) / 60000 : undefined;
      await activities.submitQuizAttempt(attempt.attempt_id, responses, elapsed);
      const detail = await activities.myAttempt(attempt.attempt_id);
      setResult(detail);
      onFinished();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [activities, attempt, responses, startedAtMs, onFinished]);

  if (error) {
    return (
      <p role="alert" className="activity-error">
        {error}
      </p>
    );
  }
  if (!quiz) return <p>Loading quiz…</p>;

  if (result) {
    const pendingManual = result.responses.filter(
      (r) => r.grading_mode === "manual" && !r.manual_graded,
    ).length;
    return (
      <section aria-label={`Result for ${quiz.title}`} className="quiz-result">
        <h4>{quiz.title}</h4>
        <p data-testid="attempt-status">Status: {result.status.replace(/_/g, " ")}</p>
        {result.status === "timed_out" && (
          <p role="alert">
            Submitted after the deadline. Your answers are saved as evidence but are not
            auto-graded — your instructor will review them.
          </p>
        )}
        <p data-testid="attempt-score">Score: {fmtScore(result.score, result.max_score)}</p>
        {pendingManual > 0 && (
          <p>{pendingManual} response(s) awaiting instructor grading.</p>
        )}
        <ul className="quiz-feedback">
          {result.responses.map((r) => (
            <li key={r.item_id}>
              <strong>{r.prompt}</strong>
              <span>
                {" "}
                — {r.points_awarded == null ? "awaiting grading" : `${r.points_awarded}/${r.max_points}`}
              </span>
              {r.manual_comment && <p className="quiz-comment">{r.manual_comment}</p>}
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (!attempt) {
    const limit = quiz.policies.time_limit_minutes;
    return (
      <section aria-label={`Start ${quiz.title}`}>
        <h4>{quiz.title}</h4>
        <p>
          {limit ? `Time limit: ${limit} minutes.` : "No time limit."}{" "}
          {quiz.policies.accommodation_applied && "Your approved accommodation is applied."}
        </p>
        {quiz.high_integrity_timed && (
          <p className="activity-note">
            This timed quiz must be taken while connected so the deadline is set by the
            school hub.
          </p>
        )}
        <button type="button" onClick={start} disabled={busy}>
          {busy ? "Starting…" : "Start attempt"}
        </button>
      </section>
    );
  }

  return (
    <section aria-label={`Attempt for ${quiz.title}`}>
      <h4>
        {quiz.title} — attempt {attempt.attempt_number}
      </h4>
      {countdown && (
        <p role="status" aria-live="polite" data-testid="quiz-countdown">
          {countdown}
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <ol className="quiz-items">
          {quiz.items.map((item) => (
            <li key={item.item_id}>
              <fieldset>
                <legend>{item.prompt}</legend>
                {item.options.length > 0 ? (
                  item.options.map((opt) => (
                    <label key={opt}>
                      <input
                        type="radio"
                        name={item.item_id}
                        value={opt}
                        checked={responses[item.item_id] === opt}
                        onChange={() =>
                          setResponses((prev) => ({ ...prev, [item.item_id]: opt }))
                        }
                      />
                      {opt}
                    </label>
                  ))
                ) : (
                  <textarea
                    aria-label={item.prompt}
                    value={responses[item.item_id] ?? ""}
                    onChange={(e) =>
                      setResponses((prev) => ({ ...prev, [item.item_id]: e.target.value }))
                    }
                  />
                )}
              </fieldset>
            </li>
          ))}
        </ol>
        <button type="submit" disabled={busy}>
          {busy ? "Submitting…" : "Submit attempt"}
        </button>
      </form>
    </section>
  );
}

function LabPanel({ activities, labId }: { activities: ActivityClient; labId: string }) {
  const [lab, setLab] = useState<LabView | null>(null);
  const [runs, setRuns] = useState<LabRunView[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [l, r] = await Promise.all([activities.getLab(labId), activities.listLabRuns(labId)]);
      setLab(l);
      setRuns(r);
    } catch (e) {
      setError(errText(e));
    }
  }, [activities, labId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await activities.completeLab(labId, newMutationId("lab"), input);
      await refresh();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [activities, labId, input, refresh]);

  if (error) {
    return (
      <p role="alert" className="activity-error">
        {error}
      </p>
    );
  }
  if (!lab) return <p>Loading lab…</p>;

  return (
    <section aria-label={`Lab ${lab.title}`}>
      <h4>{lab.title}</h4>
      <p>Mode: {lab.mode.replace(/_/g, " ").toLowerCase()}</p>
      {lab.mode === "HARDWARE" && (
        <p className="activity-note">
          Hardware evidence is captured outside this app and attached by your instructor.
        </p>
      )}
      {lab.mode === "LOCAL_SOFTWARE" && (
        <>
          <label htmlFor={`lab-input-${labId}`}>Your work</label>
          <textarea
            id={`lab-input-${labId}`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <p className="activity-note">
            The school hub runs the approved checker and records the result. Evidence hashes
            are computed on the server, not on this device.
          </p>
          <button type="button" onClick={run} disabled={busy}>
            {busy ? "Running…" : "Run check"}
          </button>
        </>
      )}
      <h5>Previous runs</h5>
      {runs.length === 0 ? (
        <p>No runs recorded yet.</p>
      ) : (
        <ul className="lab-runs">
          {runs.map((r) => (
            <li key={r.run_id} data-testid="lab-run">
              <span>{r.status}</span>
              <span> — evidence from {r.evidence_source}</span>
              {r.runner_truncated ? <span> (output truncated)</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DiscussionPanel({
  activities,
  sectionId,
  threads,
  onChanged,
}: {
  activities: ActivityClient;
  sectionId: string;
  threads: ThreadView[];
  onChanged: () => void;
}) {
  const [openThread, setOpenThread] = useState<string | null>(null);
  const [posts, setPosts] = useState<PostView[]>([]);
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadPosts = useCallback(
    async (threadId: string) => {
      setOpenThread(threadId);
      try {
        setPosts(await activities.listPosts(threadId));
      } catch (e) {
        setError(errText(e));
      }
    },
    [activities],
  );

  return (
    <section aria-label="Discussions">
      <h4>Discussions</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!title.trim()) return;
          try {
            await activities.createThread(sectionId, title.trim());
            setTitle("");
            onChanged();
          } catch (err) {
            setError(errText(err));
          }
        }}
      >
        <label htmlFor="new-thread-title">New discussion title</label>
        <input
          id="new-thread-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button type="submit">Start discussion</button>
      </form>
      <ul className="thread-list">
        {threads.map((t) => (
          <li key={t.thread_id}>
            <button type="button" onClick={() => void loadPosts(t.thread_id)}>
              {t.title}
            </button>
            {t.locked ? <span> (locked)</span> : null}
          </li>
        ))}
      </ul>
      {openThread && (
        <div aria-label="Thread posts">
          <ul className="post-list">
            {posts.map((p) => (
              <li key={p.post_id} data-testid="discussion-post">
                {p.moderated ? (
                  <em>Removed by instructor{p.moderation_reason ? `: ${p.moderation_reason}` : ""}</em>
                ) : (
                  <span>{p.body}</span>
                )}
              </li>
            ))}
          </ul>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!body.trim()) return;
              try {
                await activities.postToThread(openThread, body.trim());
                setBody("");
                await loadPosts(openThread);
              } catch (err) {
                setError(errText(err));
              }
            }}
          >
            <label htmlFor="new-post-body">Your reply</label>
            <textarea id="new-post-body" value={body} onChange={(e) => setBody(e.target.value)} />
            <button type="submit">Post reply</button>
          </form>
        </div>
      )}
    </section>
  );
}

function GroupPanel({
  activities,
  sectionId,
}: {
  activities: ActivityClient;
  sectionId: string;
}) {
  const [groups, setGroups] = useState<GroupView[]>([]);
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    activities
      .listGroups(sectionId)
      .then(setGroups)
      .catch((e) => setError(errText(e)));
  }, [activities, sectionId]);

  if (groups.length === 0) {
    return (
      <section aria-label="Groups">
        <h4>Groups</h4>
        {error ? (
          <p role="alert" className="activity-error">
            {error}
          </p>
        ) : (
          <p>You are not in a group for this section.</p>
        )}
      </section>
    );
  }

  return (
    <section aria-label="Groups">
      <h4>Groups</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      {note && <p role="status">{note}</p>}
      {groups.map((g) => (
        <div key={g.group_id}>
          <h5>{g.name}</h5>
          <p>{g.members.length} member(s)</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                const res = await activities.groupSubmit(g.group_id, {
                  activity_id: g.group_id,
                  activity_type: "group_project",
                  payload: { text_response: content },
                  contributions: [],
                });
                setNote(`Submitted for the whole group (${res.content_hash.slice(0, 12)}…).`);
                setContent("");
              } catch (err) {
                setError(errText(err));
              }
            }}
          >
            <label htmlFor={`group-content-${g.group_id}`}>Group submission</label>
            <textarea
              id={`group-content-${g.group_id}`}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
            <button type="submit">Submit for group</button>
          </form>
        </div>
      ))}
    </section>
  );
}

export function LearnerActivities({
  activities,
  sectionId,
}: {
  activities: ActivityClient;
  sectionId: string;
}) {
  const [index, setIndex] = useState<SectionActivities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openQuiz, setOpenQuiz] = useState<string | null>(null);
  const [openLab, setOpenLab] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIndex(await activities.sectionActivities(sectionId));
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  }, [activities, sectionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const accommodationNote = useMemo(() => {
    const a = index?.accommodation;
    if (!a) return null;
    const parts: string[] = [];
    if (a.time_multiplier && a.time_multiplier !== 1) parts.push(`${a.time_multiplier}× time`);
    if (a.attempt_override) parts.push(`${a.attempt_override} attempts`);
    if (a.due_extension_minutes) parts.push(`${a.due_extension_minutes} extra minutes`);
    if (a.alternate_modality) parts.push(a.alternate_modality);
    return parts.length ? parts.join(", ") : null;
  }, [index]);

  if (error) {
    return (
      <p role="alert" className="activity-error">
        {error === "ACTIVITIES_REQUIRE_HUB"
          ? "Activities need a connection to your school hub."
          : error}
      </p>
    );
  }
  if (!index) return <p>Loading activities…</p>;

  return (
    <div className="learner-activities">
      {accommodationNote && (
        <p className="accommodation-note" data-testid="accommodation-note">
          Your approved accommodations are active: {accommodationNote}.
        </p>
      )}

      <section aria-label="Quizzes">
        <h4>Quizzes</h4>
        {index.quizzes.length === 0 && <p>No quizzes yet.</p>}
        <ul className="quiz-list">
          {index.quizzes.map((q) => {
            const attempts = q.my_attempts ?? [];
            const last = attempts[attempts.length - 1];
            return (
              <li key={q.quiz_id}>
                <button type="button" onClick={() => setOpenQuiz(q.quiz_id)}>
                  {q.title}
                </button>
                <span>
                  {" "}
                  — {attempts.length} attempt(s)
                  {last ? `, latest ${fmtScore(last.score, last.max_score)}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
        {openQuiz && (
          <QuizRunner activities={activities} quizId={openQuiz} onFinished={() => void refresh()} />
        )}
      </section>

      <section aria-label="Labs">
        <h4>Labs</h4>
        {index.labs.length === 0 && <p>No labs yet.</p>}
        <ul className="lab-list">
          {index.labs.map((l) => (
            <li key={l.lab_id}>
              <button type="button" onClick={() => setOpenLab(l.lab_id)}>
                {l.title}
              </button>
            </li>
          ))}
        </ul>
        {openLab && <LabPanel activities={activities} labId={openLab} />}
      </section>

      <DiscussionPanel
        activities={activities}
        sectionId={sectionId}
        threads={index.threads}
        onChanged={() => void refresh()}
      />
      <GroupPanel activities={activities} sectionId={sectionId} />
    </div>
  );
}
