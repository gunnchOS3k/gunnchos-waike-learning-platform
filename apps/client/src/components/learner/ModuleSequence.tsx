import { MODULE_STATUS_LABEL } from "../../lib/product/moduleStatus";
import type { ModuleStatus } from "../../lib/product/types";

export interface ModuleRow {
  id: string;
  title: string;
  order: number;
  status: ModuleStatus;
  lesson?: string;
  assignment?: string;
  quiz?: string;
  lab?: string;
  discussion?: string;
  prerequisite?: string;
}

type Props = {
  modules: ModuleRow[];
  onOpenLesson?: (id: string) => void;
};

export function ModuleSequence({ modules, onOpenLesson }: Props) {
  return (
    <section className="panel" data-testid="module-sequence">
      <h2>Modules</h2>
      {modules.length === 0 ? (
        <p className="muted">No module sequence is available for this course yet.</p>
      ) : (
        <ol>
          {modules.map((m) => (
            <li key={m.id} data-testid={`module-${m.id}`}>
              <strong>
                {m.order}. {m.title}
              </strong>
              <span className="muted"> · {MODULE_STATUS_LABEL[m.status]}</span>
              <ul className="muted">
                {m.lesson ? (
                  <li>
                    {onOpenLesson ? (
                      <button type="button" className="ghost" onClick={() => onOpenLesson(m.id)}>
                        Lesson: {m.lesson}
                      </button>
                    ) : (
                      <>Lesson: {m.lesson}</>
                    )}
                  </li>
                ) : null}
                {m.assignment ? <li>Assignment: {m.assignment}</li> : null}
                {m.quiz ? <li>Quiz: {m.quiz}</li> : null}
                {m.lab ? <li>Lab: {m.lab}</li> : null}
                {m.discussion ? <li>Discussion: {m.discussion}</li> : null}
                {m.prerequisite ? <li>Prerequisite: {m.prerequisite}</li> : null}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
