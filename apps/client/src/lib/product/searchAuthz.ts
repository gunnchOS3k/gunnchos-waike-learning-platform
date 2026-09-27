import type { SearchHit } from "./types";

const ANSWER_KEY_MARKERS = [
  "answer_key",
  "answer-key",
  "answer key",
  "answer keys",
  "instructor_solution",
  "instructor-only",
  "rubric_key",
  "solution_guide",
];

export function isAnswerKeyMaterial(title: string, snippet = "", path = ""): boolean {
  const blob = `${title} ${snippet} ${path}`.toLowerCase();
  return ANSWER_KEY_MARKERS.some((marker) => blob.includes(marker));
}

export function authorizeSearchHits(
  hits: SearchHit[],
  authorizedSectionIds: string[],
  role: string,
): SearchHit[] {
  const allowed = new Set(authorizedSectionIds);
  return hits
    .filter((hit) => allowed.has(hit.section_id))
    .filter((hit) => {
      if (role === "learner" || role === "guardian") {
        return !isAnswerKeyMaterial(hit.title, hit.snippet);
      }
      return true;
    })
    .map((hit) => ({ ...hit, authorized: true }));
}

export function matchQuery(
  query: string,
  records: Array<Omit<SearchHit, "authorized">>,
): SearchHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return records
    .filter((row) => `${row.title} ${row.snippet}`.toLowerCase().includes(q))
    .map((row) => ({ ...row, authorized: false }));
}
