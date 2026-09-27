import type { NotificationItem } from "./types";

export function sortNotifications(items: NotificationItem[]): NotificationItem[] {
  return [...items].sort((a, b) => {
    if (a.unread !== b.unread) return a.unread ? -1 : 1;
    return Date.parse(b.created_at) - Date.parse(a.created_at);
  });
}

export function notificationsFromSignals(args: {
  dueSoon?: Array<{ id: string; title: string; due_at: string; deep_link: string }>;
  returned?: Array<{ id: string; title: string; at: string; deep_link: string }>;
  feedback?: Array<{ id: string; title: string; body: string; at: string; deep_link: string }>;
  announcements?: Array<{ id: string; title: string; body: string; at: string; deep_link: string }>;
  syncConflicts?: Array<{ id: string; title: string; at: string; deep_link: string }>;
  courseChanges?: Array<{ id: string; title: string; at: string; deep_link: string }>;
  readIds?: string[];
}): NotificationItem[] {
  const read = new Set(args.readIds || []);
  const items: NotificationItem[] = [];
  for (const row of args.dueSoon || []) {
    items.push({
      id: `due:${row.id}`,
      kind: "due_soon",
      title: row.title,
      body: `Due ${row.due_at}`,
      created_at: row.due_at,
      deep_link: row.deep_link,
      unread: !read.has(`due:${row.id}`),
    });
  }
  for (const row of args.returned || []) {
    items.push({
      id: `ret:${row.id}`,
      kind: "returned",
      title: row.title,
      body: "Returned with a grade or comment",
      created_at: row.at,
      deep_link: row.deep_link,
      unread: !read.has(`ret:${row.id}`),
    });
  }
  for (const row of args.feedback || []) {
    items.push({
      id: `fb:${row.id}`,
      kind: "feedback",
      title: row.title,
      body: row.body,
      created_at: row.at,
      deep_link: row.deep_link,
      unread: !read.has(`fb:${row.id}`),
    });
  }
  for (const row of args.announcements || []) {
    items.push({
      id: `ann:${row.id}`,
      kind: "announcement",
      title: row.title,
      body: row.body,
      created_at: row.at,
      deep_link: row.deep_link,
      unread: !read.has(`ann:${row.id}`),
    });
  }
  for (const row of args.syncConflicts || []) {
    items.push({
      id: `sync:${row.id}`,
      kind: "sync_conflict",
      title: row.title,
      body: "A saved change needs your review before it can sync.",
      created_at: row.at,
      deep_link: row.deep_link,
      unread: !read.has(`sync:${row.id}`),
    });
  }
  for (const row of args.courseChanges || []) {
    items.push({
      id: `chg:${row.id}`,
      kind: "course_change",
      title: row.title,
      body: "Course content or dates were updated.",
      created_at: row.at,
      deep_link: row.deep_link,
      unread: !read.has(`chg:${row.id}`),
    });
  }
  return sortNotifications(items);
}
