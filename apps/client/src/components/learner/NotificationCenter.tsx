import type { NotificationItem } from "../../lib/product/types";

type Props = {
  items: NotificationItem[];
  onOpen: (item: NotificationItem) => void;
};

export function NotificationCenter({ items, onOpen }: Props) {
  return (
    <section className="panel" data-testid="notification-center">
      <h2>Notifications</h2>
      {items.length === 0 ? (
        <p className="muted">No new notices.</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className="ghost" data-testid={`notice-${item.id}`} onClick={() => onOpen(item)}>
                {item.unread ? "New · " : ""}
                {item.title}
                <span className="muted"> — {item.body}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
