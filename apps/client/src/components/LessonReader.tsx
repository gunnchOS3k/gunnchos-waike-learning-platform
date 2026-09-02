import { useEffect, useRef } from "react";
import type { LessonContent } from "../lib/types";

export function LessonReader({
  lesson,
  resumeOffset,
  onSavePosition,
}: {
  lesson: LessonContent;
  resumeOffset: number;
  onSavePosition: (offset: number) => void;
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = resumeOffset || lesson.resume_scroll_offset || 0;
  }, [lesson.lesson_id, resumeOffset, lesson.resume_scroll_offset]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => onSavePosition(el.scrollTop);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [lesson.lesson_id, onSavePosition]);

  return (
    <article className="lesson-reader" aria-labelledby="lesson-title">
      <h2 id="lesson-title">{lesson.title}</h2>
      <section
        ref={ref}
        className="lesson-body"
        tabIndex={0}
        data-testid="lesson-body"
      >
        <pre>{lesson.markdown}</pre>
      </section>
    </article>
  );
}
