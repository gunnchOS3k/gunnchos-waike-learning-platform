/**
 * Activity engine surface (quizzes, labs, discussions, groups, accommodations).
 *
 * The answer-key call lives only on the instructor client type so a learner screen
 * cannot reach it by construction; the server enforces the same rule.
 */

export interface QuizItemView {
  item_id: string;
  ordinal: number;
  item_type: string;
  prompt: string;
  options: string[];
  max_points: number;
  grading_mode: "auto" | "manual" | string;
}

export interface QuizPolicies {
  time_limit_minutes?: number | null;
  attempt_limit?: number | null;
  accommodation_applied?: boolean;
  [k: string]: unknown;
}

export interface LearnerQuizView {
  quiz_id: string;
  title: string;
  section_id: string;
  offline_eligible: boolean;
  high_integrity_timed: boolean;
  policies: QuizPolicies;
  items: QuizItemView[];
}

export interface QuizAttemptSummary {
  attempt_id: string;
  attempt_number: number;
  status: string;
  score: number | null;
  max_score: number | null;
  deadline_at: string | null;
}

export interface QuizAttemptStart {
  attempt_id: string;
  attempt_number: number;
  started_at: string;
  deadline_at: string | null;
  time_limit_minutes: number | null;
  status: string;
}

export interface QuizAttemptResult {
  attempt_id: string;
  status: string;
  score: number | null;
  max_score: number | null;
  pending_manual: number;
  timed_out?: boolean;
  server_deadline_at?: string | null;
}

/** What a learner may see about their own attempt. No answer key, ever. */
export interface LearnerAttemptDetail {
  attempt_id: string;
  quiz_id: string;
  learner_id: string;
  status: string;
  score: number | null;
  max_score: number | null;
  started_at: string;
  deadline_at: string | null;
  submitted_at: string | null;
  responses: Array<{
    item_id: string;
    prompt: string;
    grading_mode: string;
    response: string;
    points_awarded: number | null;
    max_points: number;
    manual_graded: number;
    manual_comment: string | null;
  }>;
}

/** The grading view, including items the learner left unanswered. */
export interface InstructorAttemptDetail {
  attempt_id: string;
  quiz_id: string;
  learner_id: string;
  section_id: string;
  status: string;
  score: number | null;
  max_score: number | null;
  server_timed_out: boolean;
  deadline_at: string | null;
  submitted_at: string | null;
  items: Array<{
    item_id: string;
    ordinal: number;
    item_type: string;
    prompt: string;
    max_points: number;
    grading_mode: string;
    response: unknown;
    points_earned: number | null;
    auto_graded: boolean;
    manual_graded: boolean;
    manual_comment: string | null;
  }>;
}

export interface ManualQueueRow {
  attempt_id: string;
  learner_id: string;
  quiz_id: string;
  status: string;
  submitted_at: string | null;
  score: number | null;
  max_score: number | null;
  pending_manual: number;
}

export interface LabView {
  lab_id: string;
  title: string;
  mode: string;
  section_id: string;
  instructions?: string;
  offline_eligible: boolean;
  runner_id?: string | null;
  requires_hardware?: boolean;
}

export interface LabRunView {
  run_id: string;
  lab_id: string;
  learner_id: string;
  status: string;
  evidence_source: string;
  computed_evidence: Record<string, unknown> | null;
  runner_id: string | null;
  runner_exit_code: number | null;
  runner_duration_ms: number | null;
  runner_truncated: number | null;
  completed_at: string | null;
}

export interface ThreadView {
  thread_id: string;
  title: string;
  locked: number;
}

export interface PostView {
  post_id: string;
  thread_id: string;
  author_id: string;
  body: string;
  created_at: string;
  moderated: number;
  moderation_reason: string | null;
}

export interface GroupView {
  group_id: string;
  name: string;
  section_id: string;
  members: string[];
}

export interface GroupSubmissionView {
  group_submission_id: string;
  group_id: string;
  submitted_by: string;
  content_hash: string;
  submitted_at: string;
}

export interface GroupSubmitBody {
  activity_id: string;
  activity_type: string;
  payload: Record<string, unknown>;
  contributions: Array<Record<string, unknown>>;
}

export interface AccommodationView {
  learner_id?: string;
  section_id?: string;
  time_multiplier: number;
  attempt_override: number | null;
  due_extension_minutes: number;
  alternate_modality: string | null;
}

export interface SectionActivities {
  section_id: string;
  is_staff: boolean;
  quizzes: Array<{
    quiz_id: string;
    title: string;
    offline_eligible: boolean;
    high_integrity_timed: boolean;
    time_limit_minutes: number | null;
    attempt_limit: number | null;
    my_attempts?: QuizAttemptSummary[];
    pending_manual?: number;
  }>;
  labs: Array<{ lab_id: string; title: string; mode: string; offline_eligible: boolean }>;
  threads: ThreadView[];
  accommodation: AccommodationView | null;
}

export interface GradingProgress {
  section_id: string;
  total: number;
  graded: number;
  ungraded: number;
  percent: number;
}

/** Everything both roles may call. */
export interface ActivityClient {
  sectionActivities(sectionId: string): Promise<SectionActivities>;
  getQuiz(quizId: string): Promise<LearnerQuizView>;
  startQuizAttempt(quizId: string): Promise<QuizAttemptStart>;
  submitQuizAttempt(
    attemptId: string,
    responses: Record<string, unknown>,
    clientElapsedMinutes?: number,
  ): Promise<QuizAttemptResult>;
  /** The caller's own attempt; the server refuses another learner's id. */
  myAttempt(attemptId: string): Promise<LearnerAttemptDetail>;
  getLab(labId: string): Promise<LabView>;
  completeLab(
    labId: string,
    clientMutationId: string,
    learnerInput: string,
  ): Promise<LabRunView>;
  listLabRuns(labId: string): Promise<LabRunView[]>;
  listThreads(sectionId: string): Promise<ThreadView[]>;
  listPosts(threadId: string): Promise<PostView[]>;
  createThread(sectionId: string, title: string): Promise<ThreadView>;
  postToThread(threadId: string, body: string): Promise<PostView>;
  listGroups(sectionId: string): Promise<GroupView[]>;
  listGroupSubmissions(groupId: string): Promise<GroupSubmissionView[]>;
  groupSubmit(groupId: string, body: GroupSubmitBody): Promise<GroupSubmissionView>;
  getAccommodation(learnerId: string, sectionId: string): Promise<AccommodationView | null>;
}

/** Staff-only surface; never composed into the learner client. */
export interface InstructorActivityClient {
  answerKey(quizId: string): Promise<{ quiz_id: string; answer_key: Record<string, unknown> }>;
  manualQueue(sectionId: string, anonymous?: boolean): Promise<ManualQueueRow[]>;
  attemptDetail(attemptId: string): Promise<InstructorAttemptDetail>;
  manualGrade(
    attemptId: string,
    itemId: string,
    points: number,
    comment: string,
  ): Promise<QuizAttemptResult>;
  nextUngraded(sectionId: string, anonymous?: boolean): Promise<Record<string, unknown>>;
  gradingProgress(sectionId: string): Promise<GradingProgress>;
  moderatePost(postId: string, note: string, remove?: boolean): Promise<PostView>;
  createGroup(sectionId: string, name: string, memberIds: string[]): Promise<GroupView>;
  upsertAccommodation(body: {
    learner_id: string;
    section_id: string;
    time_multiplier?: number | null;
    availability_extension_minutes?: number | null;
    attempt_override?: number | null;
    due_extension_minutes?: number | null;
    alternate_modality?: string | null;
    notes_private?: string | null;
  }): Promise<AccommodationView>;
  /** Regrade is scoped to one submission so the audit trail names what changed. */
  regradeQueue(submissionId: string, reason: string): Promise<Record<string, unknown>>;
}

type Req = <T>(path: string, init?: RequestInit) => Promise<T>;

export function createActivityClient(req: Req): ActivityClient {
  return {
    sectionActivities: (sectionId) => req(`/api/v1/sections/${sectionId}/activities`),
    getQuiz: (quizId) => req(`/api/v1/quizzes/${quizId}`),
    startQuizAttempt: (quizId) => req(`/api/v1/quizzes/${quizId}/attempts`, { method: "POST" }),
    submitQuizAttempt: (attemptId, responses, clientElapsedMinutes) =>
      req(`/api/v1/quiz-attempts/${attemptId}/submit`, {
        method: "POST",
        body: JSON.stringify({
          responses,
          // Advisory only — the server times the attempt from its own clock.
          client_elapsed_minutes: clientElapsedMinutes ?? null,
        }),
      }),
    myAttempt: (attemptId) => req(`/api/v1/quiz-attempts/${attemptId}`),
    getLab: (labId) => req(`/api/v1/labs/${labId}`),
    completeLab: (labId, clientMutationId, learnerInput) =>
      req(`/api/v1/labs/${labId}/runs`, {
        method: "POST",
        body: JSON.stringify({
          client_mutation_id: clientMutationId,
          // Data only. The interpreter, command and arguments are fixed server-side.
          learner_input: learnerInput,
        }),
      }),
    listLabRuns: (labId) => req(`/api/v1/labs/${labId}/runs`),
    listThreads: (sectionId) =>
      req(`/api/v1/discussions/threads?section_id=${encodeURIComponent(sectionId)}`),
    listPosts: (threadId) => req(`/api/v1/discussions/threads/${threadId}/posts`),
    createThread: (sectionId, title) =>
      req("/api/v1/discussions/threads", {
        method: "POST",
        body: JSON.stringify({ section_id: sectionId, title }),
      }),
    postToThread: (threadId, body) =>
      req(`/api/v1/discussions/threads/${threadId}/posts`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    listGroups: (sectionId) => req(`/api/v1/groups?section_id=${encodeURIComponent(sectionId)}`),
    listGroupSubmissions: (groupId) => req(`/api/v1/groups/${groupId}/submissions`),
    groupSubmit: (groupId, body) =>
      req(`/api/v1/groups/${groupId}/submissions`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    getAccommodation: (learnerId, sectionId) =>
      req(
        `/api/v1/accommodations/${learnerId}?section_id=${encodeURIComponent(sectionId)}`,
      ),
  };
}

export function createInstructorActivityClient(req: Req): InstructorActivityClient {
  return {
    answerKey: (quizId) => req(`/api/v1/quizzes/${quizId}/answer-key`),
    manualQueue: (sectionId, anonymous = false) =>
      req(
        `/api/v1/instructor/sections/${sectionId}/manual-queue?anonymous=${anonymous ? "true" : "false"}`,
      ),
    attemptDetail: (attemptId) => req(`/api/v1/quiz-attempts/${attemptId}`),
    manualGrade: (attemptId, itemId, points, comment) =>
      req(`/api/v1/quiz-attempts/${attemptId}/manual-grade`, {
        method: "POST",
        body: JSON.stringify({ item_id: itemId, points, comment }),
      }),
    nextUngraded: (sectionId, anonymous = false) =>
      req(
        `/api/v1/instructor/sections/${sectionId}/next-ungraded?anonymous=${anonymous ? "true" : "false"}`,
      ),
    gradingProgress: (sectionId) =>
      req(`/api/v1/instructor/sections/${sectionId}/grading-progress`),
    moderatePost: (postId, note, remove = true) =>
      req(`/api/v1/discussions/posts/${postId}/moderate`, {
        method: "POST",
        body: JSON.stringify({ note, delete: remove }),
      }),
    createGroup: (sectionId, name, memberIds) =>
      req("/api/v1/groups", {
        method: "POST",
        body: JSON.stringify({ section_id: sectionId, name, member_ids: memberIds }),
      }),
    upsertAccommodation: (body) =>
      req("/api/v1/accommodations", { method: "POST", body: JSON.stringify(body) }),
    regradeQueue: (submissionId, reason) =>
      req("/api/v1/instructor/regrade-queue", {
        method: "POST",
        body: JSON.stringify({ submission_id: submissionId, reason }),
      }),
  };
}
