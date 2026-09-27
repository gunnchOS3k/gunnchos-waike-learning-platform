import { useMemo, useState } from "react";
import type { CourseCardModel } from "../../lib/product/types";

type Props = {
  courses: CourseCardModel[];
  activeSectionId: string | null;
  onSelect: (sectionId: string) => void;
  onTogglePin: (sectionId: string) => void;
};

export function CourseLibrary({ courses, activeSectionId, onSelect, onTogglePin }: Props) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = courses.filter((c) => {
      if (!q) return true;
      return `${c.title} ${c.code} ${c.instructor || ""} ${c.site || ""}`.toLowerCase().includes(q);
    });
    return [...rows].sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)));
  }, [courses, query]);

  return (
    <section className="panel" data-testid="course-library">
      <h2>Courses</h2>
      <label className="field-label" htmlFor="course-search">
        Search courses
      </label>
      <input
        id="course-search"
        data-testid="course-search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by title or teacher"
      />
      {filtered.length === 0 ? (
        <p className="muted" data-testid="course-library-empty">
          No matching courses. You only see courses you are enrolled in.
        </p>
      ) : (
        <ul className="course-grid">
          {filtered.map((c) => (
            <li key={c.section_id} data-testid={`course-card-${c.section_id}`}>
              <article className={c.section_id === activeSectionId ? "course-tile active" : "course-tile"}>
                <h3>{c.title}</h3>
                {c.instructor ? <p className="muted">{c.instructor}</p> : null}
                {c.site || c.term ? (
                  <p className="muted">
                    {[c.site, c.term, c.status].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
                {c.progress ? <p>{c.progress.label}</p> : null}
                {c.next_item ? <p className="muted">Next: {c.next_item.title}</p> : null}
                <div className="toolbar">
                  <button type="button" data-testid={`select-course-${c.section_id}`} onClick={() => onSelect(c.section_id)}>
                    {c.section_id === activeSectionId ? "Current course" : "Open course"}
                  </button>
                  <button type="button" className="ghost" onClick={() => onTogglePin(c.section_id)}>
                    {c.pinned ? "Unpin" : "Pin"}
                  </button>
                </div>
              </article>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
