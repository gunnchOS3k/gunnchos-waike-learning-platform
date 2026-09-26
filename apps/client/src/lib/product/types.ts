/** Learner-first product types. IDs stay in data; UI should show titles. */

export type AssignmentFilter =
  | "all"
  | "due_soon"
  | "submitted"
  | "returned"
  | "missing_overdue"
  | "completed";

export type ModuleStatus =
  | "not_started"
  | "in_progress"
  | "submitted"
  | "needs_review"
  | "complete"
  | "locked";

export type AttentionKind =
  | "overdue"
  | "revision_requested"
  | "low_mastery"
  | "sync_conflict"
  | "unacknowledged";

export interface CourseCardModel {
  section_id: string;
  code: string;
  title: string;
  instructor?: string | null;
  site?: string | null;
  term?: string | null;
  status?: string | null;
  progress?: { completed: number; total: number; label: string } | null;
  next_item?: { id: string; title: string; kind: string } | null;
  pinned?: boolean;
  mastery?: { mastered: number; score: number; gap_notes: string } | null;
}

export interface AssignmentCardModel {
  assignment_id: string;
  section_id: string;
  course_title: string;
  title: string;
  due_at: string | null;
  points_possible?: number | null;
  submission_state: string;
  grade_state: string;
  filter_keys: AssignmentFilter[];
}

export interface TodayContinue {
  section_id: string;
  course_title: string;
  item_title: string;
  item_kind: "lesson" | "assignment" | "module";
  item_id: string;
  progress_label: string;
}

export interface DueSoonItem {
  assignment_id: string;
  section_id: string;
  course_title: string;
  title: string;
  due_at: string;
  status: string;
}

export interface AttentionItem {
  id: string;
  kind: AttentionKind;
  title: string;
  course_title: string;
  section_id: string;
  deep_link: string;
}

export interface FeedbackItem {
  feedback_id: string;
  body: string;
  created_at: string;
  section_id: string;
  course_title: string;
  assignment_id?: string;
  unread?: boolean;
}

export interface UpcomingItem {
  id: string;
  title: string;
  at: string;
  kind: "assignment" | "quiz" | "lab" | "event" | "remediation";
  section_id: string;
  deep_link: string;
}

export interface TodayState {
  continue_learning: TodayContinue | null;
  due_soon: DueSoonItem[];
  needs_attention: AttentionItem[];
  recent_feedback: FeedbackItem[];
  upcoming: UpcomingItem[];
  courses: CourseCardModel[];
  ask_context: { section_id: string | null; title: string | null };
}

export interface CalendarItem {
  id: string;
  title: string;
  at: string;
  kind: UpcomingItem["kind"];
  section_id: string;
  course_title: string;
  deep_link: string;
  overdue: boolean;
}

export interface SearchHit {
  id: string;
  kind: "course" | "module" | "lesson" | "assignment" | "lab" | "discussion" | "resource";
  title: string;
  snippet: string;
  section_id: string;
  authorized: boolean;
}

export interface NotificationItem {
  id: string;
  kind:
    | "due_soon"
    | "returned"
    | "feedback"
    | "announcement"
    | "sync_conflict"
    | "course_change";
  title: string;
  body: string;
  created_at: string;
  deep_link: string;
  unread: boolean;
}

export interface SchoolApp {
  app_id: string;
  label: string;
  launch_kind: "web" | "lti" | "browser_url";
  url: string;
  allowed_origins: string[];
  pinned: boolean;
  icon_label?: string;
  configured_by: "institution";
  captures_credentials: false;
}

export interface LearnerGradeRow {
  assignment_id: string;
  section_id: string;
  course_title: string;
  title: string;
  points_earned: number | null;
  points_possible: number | null;
  status: string;
  feedback?: string | null;
  pending: boolean;
}

export const ACTIVE_COURSE_KEY = "waike_active_section";
export const PINNED_COURSES_KEY = "waike_pinned_sections";
export const FEEDBACK_READ_KEY = "waike_feedback_read";
