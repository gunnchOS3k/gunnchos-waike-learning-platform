import { useCallback, useEffect, useState } from "react";
import type {
  ActivityClient,
  GradingProgress,
  InstructorActivityClient,
  ManualQueueRow,
  PostView,
  InstructorAttemptDetail,
  SectionActivities,
  ThreadView,
} from "../../lib/hub/activities";

/** Staff console for the Gate A activity engine. */

function errText(err: unknown): string {
  if (err instanceof Error) return err.message.replace(/^\d+:/, "");
  return String(err);
}

function ManualGradingQueue({
  activities,
  staff,
  sectionId,
}: {
  activities: ActivityClient;
  staff: InstructorActivityClient;
  sectionId: string;
}) {
  const [queue, setQueue] = useState<ManualQueueRow[]>([]);
  const [progress, setProgress] = useState<GradingProgress | null>(null);
  const [anonymous, setAnonymous] = useState(false);
  const [open, setOpen] = useState<InstructorAttemptDetail | null>(null);
  const [scores, setScores] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [q, p] = await Promise.all([
        staff.manualQueue(sectionId, anonymous),
        staff.gradingProgress(sectionId),
      ]);
      setQueue(q);
      setProgress(p);
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  }, [staff, sectionId, anonymous]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openAttempt = useCallback(
    async (attemptId: string) => {
      try {
        setOpen(await staff.attemptDetail(attemptId));
      } catch (e) {
        setError(errText(e));
      }
    },
    [staff],
  );

  const gradeItem = useCallback(
    async (itemId: string) => {
      if (!open) return;
      const raw = scores[itemId];
      const points = Number(raw);
      // Bounds are enforced server-side too; this only avoids a pointless round trip.
      if (raw === undefined || raw === "" || !Number.isFinite(points)) {
        setError("Enter a numeric score before saving.");
        return;
      }
      setBusy(true);
      try {
        await staff.manualGrade(open.attempt_id, itemId, points, comments[itemId] ?? "");
        setOpen(await staff.attemptDetail(open.attempt_id));
        await refresh();
        setError(null);
      } catch (e) {
        setError(errText(e));
      } finally {
        setBusy(false);
      }
    },
    [open, scores, comments, staff, refresh],
  );

  const jumpToNext = useCallback(async () => {
    try {
      const next = (await staff.nextUngraded(sectionId, anonymous)) as {
        attempt_id?: string;
        submission_id?: string;
      };
      if (next?.attempt_id) {
        await openAttempt(next.attempt_id);
      } else {
        setError("Nothing left ungraded in this section.");
      }
    } catch (e) {
      setError(errText(e));
    }
  }, [staff, sectionId, anonymous, openAttempt]);

  return (
    <section aria-label="Manual grading queue">
      <h4>Manual grading queue</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      {progress && (
        <p data-testid="grading-progress">
          {progress.graded} of {progress.total} graded ({progress.ungraded} remaining)
        </p>
      )}
      <label>
        <input
          type="checkbox"
          checked={anonymous}
          onChange={(e) => setAnonymous(e.target.checked)}
        />
        Anonymous grading
      </label>
      <button type="button" onClick={jumpToNext}>
        Next ungraded
      </button>
      {queue.length === 0 ? (
        <p>Nothing awaiting manual grading.</p>
      ) : (
        <table>
          <caption>Attempts with manual items outstanding</caption>
          <thead>
            <tr>
              <th scope="col">Learner</th>
              <th scope="col">Status</th>
              <th scope="col">Pending items</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((row) => (
              <tr key={row.attempt_id} data-testid="manual-queue-row">
                <td>{row.learner_id}</td>
                <td>{row.status.replace(/_/g, " ")}</td>
                <td>{row.pending_manual}</td>
                <td>
                  <button type="button" onClick={() => void openAttempt(row.attempt_id)}>
                    Grade
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {open && (
        <div aria-label={`Grading attempt ${open.attempt_id}`}>
          <h5>Attempt {open.attempt_id}</h5>
          <p>Status: {open.status.replace(/_/g, " ")}</p>
          {open.server_timed_out && (
            <p role="note">
              Submitted after the server deadline. Held for review rather than auto-graded.
            </p>
          )}
          <ul>
            {open.items
              .filter((r) => r.grading_mode === "manual")
              .map((r) => (
                <li key={r.item_id}>
                  <p>
                    <strong>{r.prompt}</strong>
                  </p>
                  <blockquote>{typeof r.response === "string" ? r.response : JSON.stringify(r.response)}</blockquote>
                  <label htmlFor={`points-${r.item_id}`}>Points (max {r.max_points})</label>
                  <input
                    id={`points-${r.item_id}`}
                    type="number"
                    min={0}
                    max={r.max_points}
                    step="0.5"
                    value={scores[r.item_id] ?? (r.points_earned ?? "")}
                    onChange={(e) =>
                      setScores((prev) => ({ ...prev, [r.item_id]: e.target.value }))
                    }
                  />
                  <label htmlFor={`comment-${r.item_id}`}>Comment</label>
                  <textarea
                    id={`comment-${r.item_id}`}
                    value={comments[r.item_id] ?? r.manual_comment ?? ""}
                    onChange={(e) =>
                      setComments((prev) => ({ ...prev, [r.item_id]: e.target.value }))
                    }
                  />
                  <button type="button" disabled={busy} onClick={() => void gradeItem(r.item_id)}>
                    {r.manual_graded ? "Update score" : "Save score"}
                  </button>
                </li>
              ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function AnswerKeyPanel({
  staff,
  quizzes,
}: {
  staff: InstructorActivityClient;
  quizzes: SectionActivities["quizzes"];
}) {
  const [openQuiz, setOpenQuiz] = useState<string | null>(null);
  const [key, setKey] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section aria-label="Answer keys">
      <h4>Answer keys</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      <ul>
        {quizzes.map((q) => (
          <li key={q.quiz_id}>
            <button
              type="button"
              onClick={async () => {
                try {
                  const res = await staff.answerKey(q.quiz_id);
                  setKey(res.answer_key);
                  setOpenQuiz(q.quiz_id);
                  setError(null);
                } catch (e) {
                  setError(errText(e));
                }
              }}
            >
              View key — {q.title}
            </button>
            {typeof q.pending_manual === "number" && q.pending_manual > 0 && (
              <span> ({q.pending_manual} awaiting manual grading)</span>
            )}
          </li>
        ))}
      </ul>
      {openQuiz && key && (
        <dl data-testid="answer-key">
          {Object.entries(key).map(([itemId, answer]) => (
            <div key={itemId}>
              <dt>{itemId}</dt>
              <dd>{typeof answer === "string" ? answer : JSON.stringify(answer)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function ModerationPanel({
  activities,
  staff,
  threads,
}: {
  activities: ActivityClient;
  staff: InstructorActivityClient;
  threads: ThreadView[];
}) {
  const [openThread, setOpenThread] = useState<string | null>(null);
  const [posts, setPosts] = useState<PostView[]>([]);
  const [note, setNote] = useState("Violates participation guidelines");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (threadId: string) => {
      try {
        setOpenThread(threadId);
        setPosts(await activities.listPosts(threadId));
        setError(null);
      } catch (e) {
        setError(errText(e));
      }
    },
    [activities],
  );

  return (
    <section aria-label="Discussion moderation">
      <h4>Discussion moderation</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      <ul>
        {threads.map((t) => (
          <li key={t.thread_id}>
            <button type="button" onClick={() => void load(t.thread_id)}>
              {t.title}
            </button>
          </li>
        ))}
      </ul>
      {openThread && (
        <>
          <label htmlFor="moderation-reason">Moderation reason</label>
          <input
            id="moderation-reason"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <ul>
            {posts.map((p) => (
              <li key={p.post_id} data-testid="moderation-post">
                <span>{p.moderated ? `[removed] ${p.moderation_reason ?? ""}` : p.body}</span>
                {!p.moderated && (
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await staff.moderatePost(p.post_id, note);
                        await load(openThread);
                      } catch (e) {
                        setError(errText(e));
                      }
                    }}
                  >
                    Remove post
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function AccommodationPanel({
  staff,
  sectionId,
}: {
  staff: InstructorActivityClient;
  sectionId: string;
}) {
  const [learnerId, setLearnerId] = useState("");
  const [multiplier, setMultiplier] = useState("1.5");
  const [attempts, setAttempts] = useState("");
  const [extension, setExtension] = useState("0");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section aria-label="Accommodations">
      <h4>Accommodations</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      {note && <p role="status">{note}</p>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await staff.upsertAccommodation({
              learner_id: learnerId.trim(),
              section_id: sectionId,
              time_multiplier: Number(multiplier),
              attempt_override: attempts ? Number(attempts) : null,
              due_extension_minutes: Number(extension || 0),
            });
            setNote(`Accommodation saved for ${learnerId.trim()}.`);
            setError(null);
          } catch (err) {
            setError(errText(err));
          }
        }}
      >
        <label htmlFor="acc-learner">Learner ID</label>
        <input id="acc-learner" value={learnerId} onChange={(e) => setLearnerId(e.target.value)} />
        <label htmlFor="acc-multiplier">Time multiplier</label>
        <input
          id="acc-multiplier"
          type="number"
          step="0.25"
          min="1"
          value={multiplier}
          onChange={(e) => setMultiplier(e.target.value)}
        />
        <label htmlFor="acc-attempts">Attempt override (optional)</label>
        <input
          id="acc-attempts"
          type="number"
          min="1"
          value={attempts}
          onChange={(e) => setAttempts(e.target.value)}
        />
        <label htmlFor="acc-extension">Due extension (minutes)</label>
        <input
          id="acc-extension"
          type="number"
          min="0"
          value={extension}
          onChange={(e) => setExtension(e.target.value)}
        />
        <button type="submit">Save accommodation</button>
      </form>
    </section>
  );
}

function RegradePanel({
  staff,
  sectionId,
}: {
  staff: InstructorActivityClient;
  sectionId: string;
}) {
  const [submissionId, setSubmissionId] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section aria-label="Regrade">
      <h4>Regrade</h4>
      {error && (
        <p role="alert" className="activity-error">
          {error}
        </p>
      )}
      {note && <p role="status">{note}</p>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!submissionId.trim()) {
            setError("Enter the submission to regrade.");
            return;
          }
          if (!reason.trim()) {
            setError("A regrade reason is required for the audit trail.");
            return;
          }
          try {
            await staff.regradeQueue(submissionId.trim(), reason.trim());
            setNote(`Queued ${submissionId.trim()} for regrade in ${sectionId}.`);
            setError(null);
          } catch (err) {
            setError(errText(err));
          }
        }}
      >
        <label htmlFor="regrade-submission">Submission ID</label>
        <input
          id="regrade-submission"
          value={submissionId}
          onChange={(e) => setSubmissionId(e.target.value)}
        />
        <label htmlFor="regrade-reason">Reason (recorded in the audit trail)</label>
        <input id="regrade-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button type="submit">Queue regrade</button>
      </form>
    </section>
  );
}

export function InstructorActivities({
  activities,
  staff,
  sectionId,
}: {
  activities: ActivityClient;
  staff: InstructorActivityClient;
  sectionId: string;
}) {
  const [index, setIndex] = useState<SectionActivities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    activities
      .sectionActivities(sectionId)
      .then((i) => {
        setIndex(i);
        setError(null);
      })
      .catch((e) => setError(errText(e)));
  }, [activities, sectionId]);

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
    <div className="instructor-activities">
      <ManualGradingQueue activities={activities} staff={staff} sectionId={sectionId} />
      <AnswerKeyPanel staff={staff} quizzes={index.quizzes} />
      <ModerationPanel activities={activities} staff={staff} threads={index.threads} />
      <AccommodationPanel staff={staff} sectionId={sectionId} />
      <RegradePanel staff={staff} sectionId={sectionId} />
    </div>
  );
}
