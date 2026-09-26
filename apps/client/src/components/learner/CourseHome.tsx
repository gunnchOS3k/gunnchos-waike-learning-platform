import type { CourseCardModel, DueSoonItem } from "../../lib/product/types";

type Tab = "overview" | "modules" | "assignments" | "activities" | "grades" | "discussions" | "files";

type Props = {
  course: CourseCardModel | null;
  nextDue: DueSoonItem | null;
  announcement?: string | null;
  onContinue: () => void;
  onTab: (tab: Tab) => void;
  onContact?: () => void;
};

export function CourseHome({ course, nextDue, announcement, onContinue, onTab, onContact }: Props) {
  if (!course) {
    return (
      <section className="panel" data-testid="course-home">
        <h2>Course</h2>
        <p className="muted">Select a course from Courses. Nothing is chosen automatically.</p>
      </section>
    );
  }
  return (
    <section className="panel" data-testid="course-home">
      <h2>{course.title}</h2>
      <nav className="mode-bar" aria-label="Course">
        {(
          [
            ["overview", "Overview"],
            ["modules", "Modules"],
            ["assignments", "Assignments"],
            ["activities", "Quizzes / Activities"],
            ["grades", "Grades"],
            ["discussions", "Discussions"],
            ["files", "Files"],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" className="ghost" onClick={() => onTab(id)}>
            {label}
          </button>
        ))}
      </nav>
      <p>{course.progress?.label || "Progress appears when work is recorded."}</p>
      {nextDue ? (
        <p data-testid="course-next-due">
          Next due: {nextDue.title} · {nextDue.due_at}
        </p>
      ) : (
        <p className="muted">No upcoming due date in this course.</p>
      )}
      {announcement ? <p data-testid="course-announcement">{announcement}</p> : <p className="muted">No new announcements.</p>}
      <div className="toolbar">
        <button type="button" data-testid="course-continue" onClick={onContinue}>
          Continue
        </button>
        {onContact ? (
          <button type="button" className="ghost" onClick={onContact}>
            Contact teacher
          </button>
        ) : null}
      </div>
    </section>
  );
}
