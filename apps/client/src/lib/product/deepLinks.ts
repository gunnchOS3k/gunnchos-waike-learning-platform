export type DeepLinkKind =
  | "home"
  | "course"
  | "module"
  | "lesson"
  | "assignment"
  | "quiz"
  | "lab"
  | "grades"
  | "calendar"
  | "study"
  | "portfolio";

export interface ParsedDeepLink {
  kind: DeepLinkKind;
  id: string | null;
  href: string;
  mode: string;
}

const KINDS: DeepLinkKind[] = [
  "home",
  "course",
  "module",
  "lesson",
  "assignment",
  "quiz",
  "lab",
  "grades",
  "calendar",
  "study",
  "portfolio",
];

const MODE_FOR: Record<DeepLinkKind, string> = {
  home: "home",
  course: "courses",
  module: "course",
  lesson: "study",
  assignment: "assignments",
  quiz: "assignments",
  lab: "study",
  grades: "grades",
  calendar: "calendar",
  study: "study",
  portfolio: "portfolio",
};

export function parseWaikeDeepLink(href: string): ParsedDeepLink | null {
  if (!href.startsWith("waike://")) return null;
  const rest = href.slice("waike://".length);
  const [kindRaw, ...idParts] = rest.split("/");
  const kind = KINDS.find((k) => k === kindRaw);
  if (!kind) return null;
  const id = idParts.filter(Boolean).join("/") || null;
  if (["course", "module", "lesson", "assignment", "quiz", "lab", "study"].includes(kind) && !id) {
    return null;
  }
  return { kind, id, href, mode: MODE_FOR[kind] };
}

export function buildDeepLink(kind: DeepLinkKind, id?: string): string {
  return id ? `waike://${kind}/${id}` : `waike://${kind}`;
}
