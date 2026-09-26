import { ACTIVE_COURSE_KEY, PINNED_COURSES_KEY, type CourseCardModel } from "./types";

export function loadActiveCourseId(storage: Pick<Storage, "getItem"> | null = defaultStorage()): string | null {
  if (!storage) return null;
  try {
    const value = storage.getItem(ACTIVE_COURSE_KEY);
    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

export function persistActiveCourseId(
  sectionId: string,
  storage: Pick<Storage, "setItem"> | null = defaultStorage(),
): void {
  if (!storage || !sectionId.trim()) return;
  try {
    storage.setItem(ACTIVE_COURSE_KEY, sectionId);
  } catch {
    /* private mode */
  }
}

export function resolveActiveCourse(
  authorized: CourseCardModel[],
  persistedId: string | null,
): CourseCardModel | null {
  if (authorized.length === 0) return null;
  if (persistedId) {
    const match = authorized.find((c) => c.section_id === persistedId);
    if (match) return match;
  }
  return null;
}

export function selectActiveCourse(
  authorized: CourseCardModel[],
  requestedId: string,
  persist: (id: string) => void = (id) => persistActiveCourseId(id),
): CourseCardModel | null {
  const match = authorized.find((c) => c.section_id === requestedId);
  if (!match) return null;
  persist(match.section_id);
  return match;
}

export function loadPinnedCourseIds(storage: Pick<Storage, "getItem"> | null = defaultStorage()): string[] {
  if (!storage) return [];
  try {
    const raw = storage.getItem(PINNED_COURSES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function togglePinnedCourse(
  sectionId: string,
  storage: Pick<Storage, "getItem" | "setItem"> | null = defaultStorage(),
): string[] {
  const current = loadPinnedCourseIds(storage);
  const next = current.includes(sectionId)
    ? current.filter((id) => id !== sectionId)
    : [...current, sectionId];
  if (storage) {
    try {
      storage.setItem(PINNED_COURSES_KEY, JSON.stringify(next));
    } catch {
      /* private mode */
    }
  }
  return next;
}

function defaultStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
