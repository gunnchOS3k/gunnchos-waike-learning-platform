export type ActorRole = "learner" | "instructor" | "grader" | "site_admin";

export interface SessionUser {
  user_id: string;
  username: string;
  display_name: string;
  site_id: string;
  roles: ActorRole[];
}

export interface AuthSession {
  token: string;
  user: SessionUser;
  expires_at: string;
}

/** @deprecated Prefer AuthSession; retained for mock hub resolution. */
export interface HubActor {
  actorId: string;
  role: ActorRole;
  token?: string;
}

export interface AssignmentSummary {
  assignment_id: string;
  module_id: string;
  title: string;
  week: number | null;
  current_version: number;
  portfolio_connection: number;
}

export interface AssignmentDetail extends AssignmentSummary {
  body_markdown: string;
  source_path: string;
  source_commit: string;
  rubric: {
    rubric_id: string;
    criteria: Array<{
      criterion_id: string;
      description: string;
      max_points: number;
      levels: Array<{ level_id: string; score: number; label: string; description: string }>;
    }>;
  };
}

export interface DraftState {
  draft_id: string | null;
  assignment_id: string;
  text_response: string;
  artifact_name: string | null;
  artifact_sha256: string | null;
  revision: number;
  updated_at: string | null;
}

export interface SubmissionView {
  submission_id: string;
  assignment_id: string;
  learner_id: string;
  attempt_number: number;
  status: string;
  text_response: string;
  content_hash: string;
  submitted_at: string;
  artifacts: Array<{ artifact_id: string; filename: string; sha256: string; byte_size: number }>;
  receipt: { receipt_id: string; content_hash: string; issued_at: string; immutable_payload: string } | null;
  grade: { grade_id: string; points_earned: number; points_possible: number; returned: number; revision: number } | null;
  feedback: Array<{ feedback_id: string; author_id: string; body: string; created_at: string }>;
  evaluations: Array<{ criterion_id: string; points: number; comment: string }>;
}

export interface SectionCard {
  section_id: string;
  code: string;
  title: string;
  mastery: { mastered: number; score: number; gap_notes: string } | null;
  recent_feedback: Array<{ feedback_id: string; body: string; created_at: string }>;
}

export interface GradebookMatrix {
  section_id: string;
  categories: Array<{ category_id: string; name: string; weight: number }>;
  items: Array<{ item_id: string; title: string; points_possible: number }>;
  rows: Array<{
    learner_id: string;
    display_name: string;
    overall_percent: number | null;
    cells: Record<string, { status: string; points_earned: number | null; percent: number | null }>;
  }>;
}

export class HubAuthError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status}:${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export interface HubClient {
  login(username: string, password: string, siteId?: string): Promise<AuthSession>;
  logout(): Promise<void>;
  me(): Promise<SessionUser & { session_id?: string }>;
  learnerHome(): Promise<SectionCard[]>;
  listSections(): Promise<Array<{ section_id: string; code: string; title: string }>>;
  roster(sectionId: string): Promise<Array<{ user_id: string; display_name: string; status: string }>>;
  instructorDashboard(sectionId: string): Promise<{
    section: { title: string };
    metrics: { active_enrollments: number; submissions: number; ungraded: number };
  }>;
  sectionGradebook(sectionId: string): Promise<GradebookMatrix>;
  listUsers(): Promise<Array<{ user_id: string; username: string; display_name: string; disabled: number; roles: string[] }>>;
  createUser(body: {
    username: string;
    display_name: string;
    password: string;
    roles: string[];
  }): Promise<{ user_id: string }>;
  disableUser(userId: string, disabled: boolean): Promise<void>;
  enroll(sectionId: string, userId: string): Promise<void>;
  listAssignments(): Promise<AssignmentSummary[]>;
  getAssignment(id: string): Promise<AssignmentDetail>;
  getDraft(id: string): Promise<DraftState>;
  saveDraft(id: string, text: string, artifactName?: string, artifactBase64?: string): Promise<DraftState>;
  submit(id: string, idempotencyKey: string, text?: string, sectionId?: string): Promise<SubmissionView>;
  getSubmission(id: string): Promise<SubmissionView>;
  history(id: string): Promise<Array<{ submission_id: string; attempt_number: number; status: string; submitted_at: string }>>;
  queue(id: string, sectionId?: string): Promise<Array<{ submission_id: string; learner_id: string; attempt_number: number; status: string }>>;
  grade(
    submissionId: string,
    body: {
      criterion_scores: Array<{ criterion_id: string; points: number; level_id?: string; comment?: string }>;
      feedback_body: string;
    },
  ): Promise<{
    grade: SubmissionView["grade"];
    mastery: { mastered: number; gap_notes: string };
    remediation: { status: string } | null;
    portfolio: { portfolio_id: string } | null;
  }>;
  remediation(): Promise<Array<{ plan_id: string; assignment_id: string; task_markdown: string; status: string }>>;
  portfolio(): Promise<Array<{ portfolio_id: string; title: string; evidence_hash: string; submission_id: string }>>;
  gradebook(): Promise<Array<{ assignment_id: string; points_earned: number; points_possible: number; status: string }>>;
  mastery(assignmentId: string): Promise<{ mastered?: number; gap_notes?: string; score?: number }>;
}

function authHeaders(token: string | null, actor?: HubActor): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    h.Authorization = `Bearer ${token}`;
  } else if (actor) {
    // Test mock / fixture path only
    h["X-Waike-Actor-Id"] = actor.actorId;
    h["X-Waike-Actor-Role"] = actor.role;
  }
  return h;
}

export function createHttpHubClient(
  baseUrl: string,
  getToken: () => string | null,
  onAuthFailure?: (detail: string) => void,
  actor?: HubActor,
): HubClient {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { ...authHeaders(getToken(), actor), ...(init?.headers || {}) },
    });
    if (!res.ok) {
      const body = await res.text();
      let detail = body;
      try {
        detail = JSON.parse(body).detail || body;
      } catch {
        /* raw */
      }
      if (res.status === 401 && onAuthFailure) {
        onAuthFailure(String(detail));
      }
      throw new HubAuthError(res.status, String(detail));
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }
  return {
    login: async (username, password, siteId) => {
      const body = await req<{
        token: string;
        expires_at: string;
        user: SessionUser;
      }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password, site_id: siteId ?? null }),
      });
      return { token: body.token, expires_at: body.expires_at, user: body.user };
    },
    logout: async () => {
      await req("/api/v1/auth/logout", { method: "POST" });
    },
    me: () => req("/api/v1/auth/me"),
    learnerHome: () => req("/api/v1/learner/home"),
    listSections: () => req("/api/v1/sections"),
    roster: (sectionId) => req(`/api/v1/sections/${sectionId}/roster`),
    instructorDashboard: (sectionId) => req(`/api/v1/instructor/sections/${sectionId}/dashboard`),
    sectionGradebook: (sectionId) => req(`/api/v1/sections/${sectionId}/gradebook`),
    listUsers: () => req("/api/v1/admin/users"),
    createUser: (body) => req("/api/v1/admin/users", { method: "POST", body: JSON.stringify(body) }),
    disableUser: async (userId, disabled) => {
      await req(`/api/v1/admin/users/${userId}/disable`, {
        method: "POST",
        body: JSON.stringify({ disabled }),
      });
    },
    enroll: async (sectionId, userId) => {
      await req(`/api/v1/admin/sections/${sectionId}/enrollments`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
    },
    listAssignments: () => req("/api/v1/assignments"),
    getAssignment: (id) => req(`/api/v1/assignments/${id}`),
    getDraft: (id) => req(`/api/v1/assignments/${id}/draft`),
    saveDraft: (id, text, artifactName, artifactBase64) =>
      req(`/api/v1/assignments/${id}/draft`, {
        method: "PUT",
        body: JSON.stringify({
          text_response: text,
          artifact_name: artifactName ?? null,
          artifact_base64: artifactBase64 ?? null,
        }),
      }),
    submit: (id, idempotencyKey, text, sectionId) =>
      req(`/api/v1/assignments/${id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: idempotencyKey,
          text_response: text ?? null,
          section_id: sectionId ?? null,
        }),
      }),
    getSubmission: (id) => req(`/api/v1/submissions/${id}`),
    history: (id) => req(`/api/v1/assignments/${id}/history`),
    queue: (id, sectionId) =>
      req(
        `/api/v1/instructor/assignments/${id}/queue${sectionId ? `?section_id=${encodeURIComponent(sectionId)}` : ""}`,
      ),
    grade: (submissionId, body) =>
      req(`/api/v1/instructor/submissions/${submissionId}/grade`, {
        method: "POST",
        body: JSON.stringify({ ...body, return_to_learner: true }),
      }),
    remediation: () => req("/api/v1/remediation"),
    portfolio: () => req("/api/v1/portfolio"),
    gradebook: () => req("/api/v1/gradebook"),
    mastery: (assignmentId) => req(`/api/v1/assignments/${assignmentId}/mastery`),
  };
}
