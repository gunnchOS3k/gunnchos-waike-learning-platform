import type { AssignmentCardModel, CourseCardModel } from "./types";
import contentBundleJson from "../../generated/publicCurriculumContent.json";

/**
 * Browser-safe catalog compiled from the pinned 18-track registry and package
 * matrix, with authored learner content from verified package payloads, never instructor content,
 * answer keys, enrollment state, grades, or invented server state.
 */
export type PublicTrack = {
  trackId: string;
  title: string;
  academy: string;
  level: string;
  lessons: number;
  assignments: number;
  quizzes: number;
  labs: number;
  groups: number;
  portfolio: number;
  offlinePack: boolean;
  aiPolicy: boolean;
};

export type PublicModuleRow = {
  id: string;
  title: string;
  order: number;
  status: "not_started";
  lesson: string;
  assignment?: string;
  quiz?: string;
  lab?: string;
};

export type PublicContentItem = {
  id: string;
  title: string;
  path: string;
  sha256: string;
  markdown: string;
};

export type PublicTrackContent = {
  trackId: string;
  title: string;
  packId: string;
  contentRootSha256: string;
  sourceCommit: string;
  offlinePackDeclared: boolean;
  lessons: PublicContentItem[];
  assignments: PublicContentItem[];
  quizzes: PublicContentItem[];
  labs: PublicContentItem[];
  portfolio: PublicContentItem[];
};

const CONTENT_TRACKS = contentBundleJson.tracks as PublicTrackContent[];

export const PUBLIC_CURRICULUM_SOURCE_COMMIT = "63ba9f25ac6b8d8d1b6dd118923566fd51c57b62";

export const PUBLIC_TRACKS: PublicTrack[] = [
  ["DIGITAL_CONFIDENCE", "Digital Confidence to Computer Operator", "Information Technology", "Foundation", 10, 10, 10, 10, 25, 3, true, true],
  ["IT_SUPPORT_HARDWARE", "IT Support and Hardware Foundations", "Information Technology", "Foundation", 10, 10, 10, 10, 1, 3, true, false],
  ["SOFTWARE_BUILDER", "Software Builder Zero-to-Hero", "Software", "Foundation", 10, 10, 10, 10, 1, 3, true, true],
  ["NETWORKING_INFRA", "Networking and Internet Infrastructure", "Networking", "Foundation", 10, 10, 10, 14, 1, 3, true, true],
  ["CYBER_SOC", "Cybersecurity Foundations and SOC Readiness", "Cybersecurity", "Foundation", 10, 10, 10, 13, 1, 3, true, true],
  ["DATA_DASHBOARDS", "Data, Databases, and Dashboards", "Software", "Foundation", 10, 10, 10, 10, 1, 3, true, true],
  ["AI_ML_EDGE", "AI/ML and Edge AI Foundations", "Software", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["EMBEDDED_PROTOTYPING", "Embedded Systems and Device Prototyping", "Hardware", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["WIRELESS_6G", "Wireless, DSP, and 6G Foundations", "Networking", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["PM_AGILE_LSS", "Project Management, Agile, and Lean Six Sigma", "Process and project management", "Foundation", 10, 10, 10, 10, 1, 3, true, true],
  ["GAME_DEV_INTERACTIVE", "Game Development and Interactive Media", "Software", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["SEVEN_GC_APPRENTICESHIP", "7GC AI-RAN Research Apprenticeship", "Software", "Research apprenticeship", 10, 10, 10, 10, 1, 3, true, true],
  ["CLOUD_DEVOPS", "Cloud and DevOps", "Software", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["COMM_PD_ETHICS", "Communication, Professional Development, and Ethics", "Professional development", "Foundation", 10, 10, 10, 10, 1, 3, true, true],
  ["ROBOTICS_CONTROL", "Robotics and Control", "Hardware", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["GUNNCHOS_PRODUCT_LAB", "gunnchOS Device OS and Product Lab", "Hardware", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
  ["HARDWARE_ENGINEERING", "Hardware Engineering", "Hardware", "Foundation", 10, 10, 10, 10, 1, 3, true, true],
  ["DATA_VIZ_BI", "Data Visualization and Business Intelligence", "Software", "Advanced extension", 10, 10, 10, 10, 1, 3, true, true],
].map(([trackId, title, academy, level, lessons, assignments, quizzes, labs, groups, portfolio, offlinePack, aiPolicy]) => ({
  trackId: String(trackId),
  title: String(title),
  academy: String(academy),
  level: String(level),
  lessons: Number(lessons),
  assignments: Number(assignments),
  quizzes: Number(quizzes),
  labs: Number(labs),
  groups: Number(groups),
  portfolio: Number(portfolio),
  offlinePack: Boolean(offlinePack),
  aiPolicy: Boolean(aiPolicy),
}));

const CATALOG_PREFIX = "catalog:";

export function catalogSectionId(trackId: string): string {
  return `${CATALOG_PREFIX}${trackId}`;
}

export function publicTrackForSection(sectionId: string | null): PublicTrack | null {
  if (!sectionId || !sectionId.startsWith(CATALOG_PREFIX)) return null;
  const id = sectionId.slice(CATALOG_PREFIX.length);
  return PUBLIC_TRACKS.find((track) => track.trackId === id) || null;
}

export function publicContentForTrack(track: PublicTrack | null): PublicTrackContent | null {
  if (!track) return null;
  return CONTENT_TRACKS.find((content) => content.trackId === track.trackId) || null;
}

export function publicCourseModels(pinnedIds: string[] = []): CourseCardModel[] {
  return PUBLIC_TRACKS.map((track) => ({
    section_id: catalogSectionId(track.trackId),
    code: track.level,
    title: track.title,
    site: track.academy,
    term: track.level,
    status: "Verified package catalog",
    pinned: pinnedIds.includes(catalogSectionId(track.trackId)),
    progress: null,
    summary: `${track.lessons} lessons · ${track.assignments} assignments · ${track.labs} labs${track.quizzes ? ` · ${track.quizzes} quizzes` : ""}`,
    availability: track.offlinePack ? "Offline pack declared" : "Online/package install required",
  }));
}

export function publicModulesForTrack(track: PublicTrack | null): PublicModuleRow[] {
  const content = publicContentForTrack(track);
  if (!track || !content) return [];
  return content.lessons.map((lesson, index) => {
    const n = index + 1;
    return {
      id: `${track.trackId}.unit.${n}`,
      title: lesson.title,
      order: n,
      status: "not_started" as const,
      lesson: lesson.title,
      assignment: content.assignments[index]?.title,
      quiz: content.quizzes[index]?.title,
      lab: content.labs[index]?.title,
    };
  });
}

export function publicAssignmentsForTrack(track: PublicTrack | null): AssignmentCardModel[] {
  const content = publicContentForTrack(track);
  if (!track || !content) return [];
  const sectionId = catalogSectionId(track.trackId);
  return content.assignments.map((assignment) => ({
    assignment_id: `${track.trackId}:${assignment.id}`,
    section_id: sectionId,
    course_title: track.title,
    title: assignment.title,
    due_at: null,
    points_possible: null,
    submission_state: "Requires a school Hub",
    grade_state: "none",
    filter_keys: ["all"],
  }));
}

export function publicCatalogStudyText(track: PublicTrack, unit: number): string {
  const content = publicContentForTrack(track);
  return content?.lessons[unit - 1]?.markdown || "This authored lesson could not be loaded.";
}

export function publicAssignmentContent(
  track: PublicTrack | null,
  assignmentId: string | null,
): PublicContentItem | null {
  const content = publicContentForTrack(track);
  if (!content || !assignmentId) return null;
  const id = assignmentId.split(":").at(-1);
  return content.assignments.find((item) => item.id === id) || null;
}
