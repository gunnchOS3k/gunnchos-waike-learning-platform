"""001 — Assessment lifecycle persistence (PR2)."""

SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actors (
  actor_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK(role IN ('learner','instructor','grader','site_admin')),
  display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rubrics (
  rubric_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  title TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_commit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rubric_criteria (
  criterion_id TEXT PRIMARY KEY,
  rubric_id TEXT NOT NULL REFERENCES rubrics(rubric_id),
  description TEXT NOT NULL,
  max_points REAL NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rubric_levels (
  level_id TEXT PRIMARY KEY,
  criterion_id TEXT NOT NULL REFERENCES rubric_criteria(criterion_id),
  score REAL NOT NULL,
  label TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS assignments (
  assignment_id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  title TEXT NOT NULL,
  week INTEGER,
  body_markdown TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  rubric_id TEXT NOT NULL REFERENCES rubrics(rubric_id),
  outcome_id TEXT REFERENCES outcomes(outcome_id),
  mastery_threshold REAL NOT NULL DEFAULT 3.0,
  portfolio_connection INTEGER NOT NULL DEFAULT 1,
  revision_policy TEXT NOT NULL DEFAULT 'allowed_with_changelog',
  current_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignment_versions (
  assignment_version_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id),
  version INTEGER NOT NULL,
  title TEXT NOT NULL,
  body_markdown TEXT NOT NULL,
  rubric_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(assignment_id, version)
);

CREATE TABLE IF NOT EXISTS drafts (
  draft_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id),
  learner_id TEXT NOT NULL,
  text_response TEXT NOT NULL DEFAULT '',
  artifact_name TEXT,
  artifact_bytes BLOB,
  artifact_sha256 TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  UNIQUE(assignment_id, learner_id)
);

CREATE TABLE IF NOT EXISTS submissions (
  submission_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id),
  assignment_version INTEGER NOT NULL,
  learner_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  text_response TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  idempotency_key TEXT,
  submitted_at TEXT NOT NULL,
  UNIQUE(assignment_id, learner_id, attempt_number),
  UNIQUE(learner_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS submission_revisions (
  revision_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
  revision_number INTEGER NOT NULL,
  text_response TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(submission_id, revision_number)
);

CREATE TABLE IF NOT EXISTS submission_artifacts (
  artifact_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  blob BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS submission_receipts (
  receipt_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL UNIQUE REFERENCES submissions(submission_id),
  content_hash TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  immutable_payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rubric_evaluations (
  evaluation_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
  criterion_id TEXT NOT NULL,
  level_id TEXT,
  points REAL NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  graded_by TEXT NOT NULL,
  graded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grades (
  grade_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL UNIQUE REFERENCES submissions(submission_id),
  learner_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  points_earned REAL NOT NULL,
  points_possible REAL NOT NULL,
  returned INTEGER NOT NULL DEFAULT 0,
  graded_by TEXT NOT NULL,
  graded_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS grade_audit (
  audit_id TEXT PRIMARY KEY,
  grade_id TEXT NOT NULL REFERENCES grades(grade_id),
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  feedback_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
  author_id TEXT NOT NULL,
  body TEXT NOT NULL,
  visible_to_learner INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gradebook_entries (
  entry_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  grade_id TEXT NOT NULL REFERENCES grades(grade_id),
  points_earned REAL NOT NULL,
  points_possible REAL NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(learner_id, assignment_id)
);

CREATE TABLE IF NOT EXISTS mastery_records (
  mastery_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL,
  outcome_id TEXT NOT NULL REFERENCES outcomes(outcome_id),
  assignment_id TEXT NOT NULL,
  submission_id TEXT NOT NULL,
  score REAL NOT NULL,
  threshold REAL NOT NULL,
  mastered INTEGER NOT NULL,
  gap_notes TEXT NOT NULL DEFAULT '',
  evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS remediation_plans (
  plan_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  mastery_id TEXT NOT NULL REFERENCES mastery_records(mastery_id),
  task_markdown TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_artifacts (
  portfolio_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  submission_id TEXT NOT NULL,
  title TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(learner_id, submission_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
  event_id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""
