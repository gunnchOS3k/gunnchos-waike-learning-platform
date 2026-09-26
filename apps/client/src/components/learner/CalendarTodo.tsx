import { groupCalendar } from "../../lib/product/calendarTodo";
import type { CalendarItem } from "../../lib/product/types";

type Props = {
  items: CalendarItem[];
  nowIso: string;
  timeZone?: string;
  onOpen: (deepLink: string) => void;
};

export function CalendarTodo({ items, nowIso, timeZone = "UTC", onOpen }: Props) {
  const groups = groupCalendar(items, nowIso, timeZone);
  return (
    <section className="panel" data-testid="calendar-todo">
      <h2>Calendar</h2>
      <p className="muted">Agenda from due dates already on your courses. Nothing is invented.</p>
      {(
        [
          ["overdue", "Overdue"],
          ["today", "Today"],
          ["this_week", "This week"],
          ["later", "Later"],
        ] as const
      ).map(([key, label]) => (
        <section key={key} data-testid={`calendar-${key}`}>
          <h3>{label}</h3>
          {groups[key].length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul>
              {groups[key].map((item) => (
                <li key={item.id}>
                  <button type="button" className="ghost" onClick={() => onOpen(item.deep_link)}>
                    {item.course_title} · {item.title} · {item.at}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </section>
  );
}
