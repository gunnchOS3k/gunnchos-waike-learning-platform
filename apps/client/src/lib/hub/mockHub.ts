import type {
  AssignmentDetail,
  AssignmentSummary,
  DraftState,
  HubActor,
  HubClient,
  SubmissionView,
} from "./client";

type Store = {
  draft: DraftState;
  submissions: Array<SubmissionView & { idem?: string }>;
  remediation: Array<{ plan_id: string; assignment_id: string; task_markdown: string; status: string }>;
  portfolio: Array<{ portfolio_id: string; title: string; evidence_hash: string; submission_id: string }>;
  gradebook: Array<{ assignment_id: string; points_earned: number; points_possible: number; status: string }>;
  mastery: { mastered?: number; gap_notes?: string; score?: number };
};

const assignment: AssignmentDetail = {
  assignment_id: "digital_confidence_w01",
  module_id: "DIGITAL_CONFIDENCE",
  title: "Mental model reflection",
  week: 1,
  current_version: 1,
  portfolio_connection: 1,
  body_markdown:
    "# Assignment 01: Why digital confidence matters\n\nWrite a one-page reflection on what digital confidence means in your community.",
  source_path: "assignments/by_course/digital_confidence/week_01.yaml",
  source_commit: "e97e74fc9bfb44b1cdc26b272dc4848264f15fe0",
  rubric: {
    rubric_id: "rubric_master_waike_v1",
    criteria: [
      {
        criterion_id: "crit_conceptual_understanding",
        description: "conceptual understanding",
        max_points: 4,
        levels: [
          { level_id: "L4", score: 4, label: "Level 4", description: "Exceeds" },
          { level_id: "L2", score: 2, label: "Level 2", description: "Developing" },
        ],
      },
    ],
  },
};

function freshStore(): Store {
  return {
    draft: {
      draft_id: null,
      assignment_id: assignment.assignment_id,
      text_response: "",
      artifact_name: null,
      artifact_sha256: null,
      revision: 0,
      updated_at: null,
    },
    submissions: [],
    remediation: [],
    portfolio: [],
    gradebook: [],
    mastery: {},
  };
}

/** Shared across actor role switches in the browser shell / Vitest. */
let STORE: Store = freshStore();

export function resetMockHubStore(): void {
  STORE = freshStore();
}

/** Deterministic in-browser/Vitest hub stand-in for UI flows (server E2E is authoritative). */
export function createMockHubClient(actor: HubActor): HubClient {
  const instructorSide = actor.role === "instructor" || actor.role === "grader" || actor.role === "site_admin";
  return {
    async login(username, _password, siteId) {
      return {
        token: `mock-token-${username}`,
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
        user: {
          user_id: username,
          username,
          display_name: username,
          site_id: siteId || "site-alpha",
          roles: [actor.role],
        },
      };
    },
    async logout() {},
    async me() {
      return {
        user_id: actor.actorId,
        username: actor.actorId,
        display_name: actor.actorId,
        site_id: "site-alpha",
        roles: [actor.role],
      };
    },
    async learnerHome() {
      return [
        {
          section_id: "sec_alpha_dc_w01",
          code: "DC-W01-A",
          title: "Digital Confidence — Alpha",
          mastery: STORE.mastery.mastered != null
            ? {
                mastered: STORE.mastery.mastered || 0,
                score: STORE.mastery.score || 0,
                gap_notes: STORE.mastery.gap_notes || "",
              }
            : null,
          recent_feedback: STORE.submissions.flatMap((s) => s.feedback).slice(0, 3),
        },
      ];
    },
    async listSections() {
      return [{ section_id: "sec_alpha_dc_w01", code: "DC-W01-A", title: "Digital Confidence — Alpha" }];
    },
    async roster() {
      if (!instructorSide) throw new Error("403");
      return [
        { user_id: "learner-a", display_name: "Learner A", status: "active" },
        { user_id: "learner-b", display_name: "Learner B", status: "active" },
      ];
    },
    async instructorDashboard() {
      if (!instructorSide) throw new Error("403");
      return {
        section: { title: "Digital Confidence — Alpha" },
        metrics: {
          active_enrollments: 2,
          submissions: STORE.submissions.length,
          ungraded: STORE.submissions.filter((s) => !s.grade).length,
        },
      };
    },
    async sectionGradebook() {
      return {
        section_id: "sec_alpha_dc_w01",
        categories: [{ category_id: "c1", name: "Assignments", weight: 1 }],
        items: [{ item_id: "i1", title: "Week 01", points_possible: 20 }],
        rows:
          actor.role === "learner"
            ? [
                {
                  learner_id: actor.actorId,
                  display_name: actor.actorId,
                  overall_percent: STORE.gradebook[0]
                    ? (STORE.gradebook[0].points_earned / STORE.gradebook[0].points_possible) * 100
                    : null,
                  cells: {},
                },
              ]
            : [
                {
                  learner_id: "learner-a",
                  display_name: "Learner A",
                  overall_percent: 80,
                  cells: { i1: { status: "graded", points_earned: 16, percent: 80 } },
                },
              ],
      };
    },
    async listUsers() {
      if (actor.role !== "site_admin") throw new Error("403");
      return [
        {
          user_id: "learner-a",
          username: "learner-a",
          display_name: "Learner A",
          disabled: 0,
          roles: ["learner"],
        },
      ];
    },
    async createUser() {
      return { user_id: "user_new" };
    },
    async disableUser() {},
    async enroll() {},
    async listAssignments(): Promise<AssignmentSummary[]> {
      return [assignment];
    },
    async getAssignment() {
      return assignment;
    },
    async getDraft() {
      return { ...STORE.draft };
    },
    async saveDraft(_id, text, artifactName) {
      STORE.draft = {
        ...STORE.draft,
        draft_id: STORE.draft.draft_id || "draft_mock",
        text_response: text,
        artifact_name: artifactName ?? STORE.draft.artifact_name,
        artifact_sha256: artifactName ? "mocksha" : STORE.draft.artifact_sha256,
        revision: STORE.draft.revision + 1,
        updated_at: new Date().toISOString(),
      };
      return { ...STORE.draft };
    },
    async submit(_id, idempotencyKey, text) {
      const existing = STORE.submissions.find((s) => s.idem === idempotencyKey);
      if (existing) return existing;
      const sub: SubmissionView & { idem?: string } = {
        submission_id: `sub_${STORE.submissions.length + 1}`,
        assignment_id: assignment.assignment_id,
        learner_id: actor.actorId,
        attempt_number: STORE.submissions.length + 1,
        status: "submitted",
        text_response: text || STORE.draft.text_response,
        content_hash: "a".repeat(64),
        submitted_at: new Date().toISOString(),
        artifacts: STORE.draft.artifact_name
          ? [
              {
                artifact_id: "art1",
                filename: STORE.draft.artifact_name,
                sha256: "b".repeat(64),
                byte_size: 12,
              },
            ]
          : [],
        receipt: {
          receipt_id: "rcpt1",
          content_hash: "a".repeat(64),
          issued_at: new Date().toISOString(),
          immutable_payload: "{}",
        },
        grade: null,
        feedback: [],
        evaluations: [],
        idem: idempotencyKey,
      };
      STORE.submissions.push(sub);
      return sub;
    },
    async getSubmission(id) {
      const s = STORE.submissions.find((x) => x.submission_id === id);
      if (!s) throw new Error("404");
      if (actor.role === "learner" && s.learner_id !== actor.actorId) {
        throw new Error("403:FORBIDDEN_OTHER_LEARNER");
      }
      return s;
    },
    async history() {
      return STORE.submissions
        .filter((s) => instructorSide || s.learner_id === actor.actorId)
        .map((s) => ({
          submission_id: s.submission_id,
          attempt_number: s.attempt_number,
          status: s.status,
          submitted_at: s.submitted_at,
        }));
    },
    async queue() {
      if (!instructorSide) throw new Error("403");
      return STORE.submissions.map((s) => ({
        submission_id: s.submission_id,
        learner_id: s.learner_id,
        attempt_number: s.attempt_number,
        status: s.status,
      }));
    },
    async grade(submissionId, body) {
      if (!instructorSide) throw new Error("403");
      const s = STORE.submissions.find((x) => x.submission_id === submissionId);
      if (!s) throw new Error("404");
      const pts = body.criterion_scores.reduce((a, c) => a + c.points, 0);
      const possible = Math.max(body.criterion_scores.length, 1) * 4;
      s.grade = {
        grade_id: "grd1",
        points_earned: pts,
        points_possible: possible,
        returned: 1,
        revision: (s.grade?.revision || 0) + 1,
      };
      s.feedback = [
        {
          feedback_id: "fb1",
          author_id: actor.actorId,
          body: body.feedback_body,
          created_at: new Date().toISOString(),
        },
      ];
      s.evaluations = body.criterion_scores.map((c) => ({
        criterion_id: c.criterion_id,
        points: c.points,
        comment: c.comment || "",
      }));
      s.status = "returned";
      const avg = pts / Math.max(body.criterion_scores.length, 1);
      const mastered = avg >= 3 ? 1 : 0;
      STORE.mastery = {
        mastered,
        gap_notes: mastered ? "" : "gap",
        score: avg,
      };
      STORE.gradebook = [
        {
          assignment_id: assignment.assignment_id,
          points_earned: pts,
          points_possible: possible,
          status: "returned",
        },
      ];
      let rem = null;
      let port = null;
      if (!mastered) {
        STORE.remediation = [
          {
            plan_id: "rem1",
            assignment_id: assignment.assignment_id,
            task_markdown: "Revise reflection",
            status: "assigned",
          },
        ];
        rem = STORE.remediation[0];
      } else {
        STORE.remediation = STORE.remediation.map((r) => ({ ...r, status: "completed" }));
        port = { portfolio_id: "port1" };
        STORE.portfolio = [
          {
            portfolio_id: "port1",
            title: "Portfolio evidence — Mental model reflection",
            evidence_hash: s.content_hash,
            submission_id: s.submission_id,
          },
        ];
      }
      return {
        grade: s.grade,
        mastery: { mastered, gap_notes: STORE.mastery.gap_notes || "" },
        remediation: rem,
        portfolio: port,
      };
    },
    async remediation() {
      return STORE.remediation;
    },
    async portfolio() {
      return STORE.portfolio;
    },
    async gradebook() {
      return STORE.gradebook;
    },
    async mastery() {
      return STORE.mastery;
    },
  };
}
