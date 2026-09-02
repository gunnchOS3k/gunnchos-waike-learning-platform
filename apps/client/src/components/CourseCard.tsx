import type { LessonInfo, ModuleView } from "../lib/types";

export function CourseCard({
  module,
  onOpenLesson,
}: {
  module: ModuleView;
  onOpenLesson: (lesson: LessonInfo) => void;
}) {
  return (
    <section className="course-card" aria-labelledby="course-title">
      <h2 id="course-title">{module.title}</h2>
      <p className="muted">Module {module.module_id}</p>
      <ol className="lesson-list">
        {module.lessons.map((lesson) => (
          <li key={lesson.lesson_id}>
            <button
              type="button"
              className="lesson-link"
              onClick={() => onOpenLesson(lesson)}
            >
              {lesson.title}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
