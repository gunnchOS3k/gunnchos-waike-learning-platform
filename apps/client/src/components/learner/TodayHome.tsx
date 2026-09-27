import type { TodayState } from "../../lib/product/types";

type Props = {
  today: TodayState;
  onContinue: () => void;
  onOpenAssignment: (id: string, sectionId: string) => void;
  onOpenCourse: (sectionId: string) => void;
  onOpenCalendar: () => void;
  onAsk: () => void;
};

export function TodayHome({ today, onContinue, onOpenAssignment, onOpenCourse, onOpenCalendar, onAsk }: Props) {
  return (
    <section className="panel today-home" data-testid="learner-home">
      <h2>Today</h2>
      <p className="muted">What needs your time next — not a dump of every course file.</p>

      <section data-testid="today-continue">
        <h3>Continue learning</h3>
        {today.continue_learning ? (
          <div className="card-row">
            <div>
              <strong>{today.continue_learning.course_title}</strong>
              <p className="muted">
                {today.continue_learning.item_title} · {today.continue_learning.progress_label}
              </p>
            </div>
            <button type="button" data-testid="continue-cta" onClick={onContinue}>
              Continue
            </button>
          </div>
        ) : (
          <p className="muted">Choose a course to pick up where you left off.</p>
        )}
      </section>

      <section data-testid="today-due-soon">
        <h3>Due soon</h3>
        {today.due_soon.length === 0 ? (
          <p className="muted">Nothing due in the next window.</p>
        ) : (
          <ul>
            {today.due_soon.map((item) => (
              <li key={item.assignment_id}>
                <button
                  type="button"
                  className="ghost"
                  data-testid={`due-soon-${item.assignment_id}`}
                  onClick={() => onOpenAssignment(item.assignment_id, item.section_id)}
                >
                  {item.course_title} · {item.title} · due {item.due_at} · {item.status}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="today-attention">
        <h3>Needs attention</h3>
        {today.needs_attention.length === 0 ? (
          <p className="muted">You’re caught up.</p>
        ) : (
          <ul>
            {today.needs_attention.map((item) => (
              <li key={item.id}>
                {item.course_title} · {item.title}
                <span className="muted"> · {item.kind.replace(/_/g, " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="today-feedback">
        <h3>Recent feedback</h3>
        {today.recent_feedback.length === 0 ? (
          <p className="muted">No returned comments yet.</p>
        ) : (
          <ul>
            {today.recent_feedback.map((item) => (
              <li key={item.feedback_id}>
                <button
                  type="button"
                  className="ghost"
                  data-testid={`feedback-${item.feedback_id}`}
                  onClick={() => item.assignment_id && onOpenAssignment(item.assignment_id, item.section_id)}
                >
                  {item.course_title}: {item.body}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="today-upcoming">
        <h3>Upcoming</h3>
        {today.upcoming.length === 0 ? (
          <p className="muted">No upcoming dates.</p>
        ) : (
          <ul>
            {today.upcoming.map((item) => (
              <li key={item.id}>
                {item.title} · {item.at}
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="ghost" onClick={onOpenCalendar}>
          Open calendar
        </button>
      </section>

      <section data-testid="today-courses">
        <h3>Courses</h3>
        {today.courses.length === 0 ? (
          <p className="muted">No courses yet. Ask your school if you expected to see one.</p>
        ) : (
          <ul>
            {today.courses.map((c) => (
              <li key={c.section_id}>
                <button type="button" className="ghost" onClick={() => onOpenCourse(c.section_id)}>
                  {c.title}
                  {c.progress ? ` · ${c.progress.label}` : ""}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section data-testid="today-ask">
        <h3>Ask gunnchAI</h3>
        <p className="muted">
          {today.ask_context.title
            ? `Help stays in ${today.ask_context.title}. No answer keys.`
            : "Help after you open a course. No answer keys."}
        </p>
        <button type="button" data-testid="ask-gunnchai" onClick={onAsk}>
          Ask gunnchAI
        </button>
      </section>
    </section>
  );
}
