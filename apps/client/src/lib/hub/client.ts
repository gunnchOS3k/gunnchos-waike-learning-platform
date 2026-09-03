export type ActorRole = "learner" | "instructor";

export interface HubActor {
  actorId: string;
  role: ActorRole;
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

export interface HubClient {
  listAssignments(): Promise<AssignmentSummary[]>;
  getAssignment(id: string): Promise<AssignmentDetail>;
  getDraft(id: string): Promise<DraftState>;
  saveDraft(id: string, text: string, artifactName?: string, artifactBase64?: string): Promise<DraftState>;
  submit(id: string, idempotencyKey: string, text?: string): Promise<SubmissionView>;
  getSubmission(id: string): Promise<SubmissionView>;
  history(id: string): Promise<Array<{ submission_id: string; attempt_number: number; status: string; submitted_at: string }>>;
  queue(id: string): Promise<Array<{ submission_id: string; learner_id: string; attempt_number: number; status: string }>>;
  grade(
    submissionId: string,
    body: {
      criterion_scores: Array<{ criterion_id: string; points: number; level_id?: string; comment?: string }>;
      feedback_body: string;
      force_mastery_gap?: boolean | null;
    },
  ): Promise<{ grade: SubmissionView["grade"]; mastery: { mastered: number; gap_notes: string }; remediation: { status: string } | null; portfolio: { portfolio_id: string } | null }>;
  remediation(): Promise<Array<{ plan_id: string; assignment_id: string; task_markdown: string; status: string }>>;
  portfolio(): Promise<Array<{ portfolio_id: string; title: string; evidence_hash: string; submission_id: string }>>;
  gradebook(): Promise<Array<{ assignment_id: string; points_earned: number; points_possible: number; status: string }>>;
  mastery(assignmentId: string): Promise<{ mastered?: number; gap_notes?: string; score?: number }>;
}

function headers(actor: HubActor): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Waike-Actor-Id": actor.actorId,
    "X-Waike-Actor-Role": actor.role,
  };
}

export function createHttpHubClient(baseUrl: string, actor: HubActor): HubClient {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { ...headers(actor), ...(init?.headers || {}) },
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`${res.status}:${body}`);
    }
    return (await res.json()) as T;
  }
  return {
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
    submit: (id, idempotencyKey, text) =>
      req(`/api/v1/assignments/${id}/submit`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: idempotencyKey, text_response: text ?? null }),
      }),
    getSubmission: (id) => req(`/api/v1/submissions/${id}`),
    history: (id) => req(`/api/v1/assignments/${id}/history`),
    queue: (id) => req(`/api/v1/instructor/assignments/${id}/queue`),
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
