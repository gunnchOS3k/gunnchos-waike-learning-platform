"""Gate A: offline leases, sync mutations/receipts, activity engine tables.

Forward-only and never shipped to main before Gate A, so constraints live here rather
than in a follow-up ALTER migration. Referential integrity is enforced by SQLite
(`PRAGMA foreign_keys = ON` in ``app.db.connect``); tenancy uniqueness is site-scoped so
one site can never collide with, or read, another site's rows.
"""

SQL = """
CREATE TABLE IF NOT EXISTS offline_leases (
  lease_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  device_id TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  revoke_reason TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  CHECK (length(device_id) > 0)
);
CREATE INDEX IF NOT EXISTS idx_offline_leases_user ON offline_leases(user_id, section_id);
CREATE INDEX IF NOT EXISTS idx_offline_leases_section ON offline_leases(section_id);
CREATE INDEX IF NOT EXISTS idx_offline_leases_site ON offline_leases(site_id);

CREATE TABLE IF NOT EXISTS sync_mutations (
  client_mutation_id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  device_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL DEFAULT 0,
  operation TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  local_sequence INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sync_status TEXT NOT NULL CHECK (sync_status IN (
    'pending','syncing','acknowledged','conflict','rejected','retryable_error','quarantined'
  )),
  server_revision INTEGER,
  result_json TEXT,
  acknowledged_at TEXT,
  UNIQUE(actor_id, client_mutation_id),
  CHECK (base_revision >= 0),
  CHECK (length(payload_hash) = 64)
);
CREATE INDEX IF NOT EXISTS idx_sync_mutations_entity ON sync_mutations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_sync_mutations_status ON sync_mutations(sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_mutations_scope ON sync_mutations(site_id, section_id, actor_id);

CREATE TABLE IF NOT EXISTS sync_receipts (
  receipt_id TEXT PRIMARY KEY,
  client_mutation_id TEXT NOT NULL UNIQUE REFERENCES sync_mutations(client_mutation_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  authoritative_revision INTEGER NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('ok','conflict','rejected','quarantined')),
  payload_hash TEXT,
  server_timestamp TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sync_receipts_actor ON sync_receipts(actor_id);
CREATE INDEX IF NOT EXISTS idx_sync_receipts_scope ON sync_receipts(site_id, section_id);

CREATE TABLE IF NOT EXISTS entity_revisions (
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  actor_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (entity_type, entity_id, revision),
  CHECK (revision > 0)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
  progress_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  pack_id TEXT NOT NULL,
  lesson_id TEXT NOT NULL,
  path TEXT NOT NULL DEFAULT '',
  scroll_offset REAL NOT NULL DEFAULT 0,
  percent_complete REAL NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, section_id, pack_id, lesson_id),
  CHECK (percent_complete >= 0 AND percent_complete <= 100),
  CHECK (scroll_offset >= 0),
  CHECK (revision > 0)
);
CREATE INDEX IF NOT EXISTS idx_lesson_progress_scope ON lesson_progress(section_id, user_id, revision);

CREATE TABLE IF NOT EXISTS draft_versions (
  version_id TEXT PRIMARY KEY,
  draft_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(draft_key, revision),
  CHECK (revision > 0)
);
CREATE INDEX IF NOT EXISTS idx_draft_versions_scope ON draft_versions(section_id, user_id, revision);

CREATE TABLE IF NOT EXISTS attachment_blobs (
  blob_id TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL,
  filename TEXT NOT NULL,
  safe_filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  storage_path TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0 CHECK (quarantined IN (0,1)),
  quarantine_reason TEXT,
  uploaded_by TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  created_at TEXT NOT NULL,
  -- Tenancy: dedup may only ever collapse blobs inside one site.
  UNIQUE(site_id, content_hash),
  CHECK (byte_size >= 0),
  CHECK (length(content_hash) = 64)
);
CREATE INDEX IF NOT EXISTS idx_attachment_blobs_section ON attachment_blobs(site_id, section_id);

CREATE TABLE IF NOT EXISTS quiz_definitions (
  quiz_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  title TEXT NOT NULL,
  policies_json TEXT NOT NULL,
  answer_key_json TEXT NOT NULL,
  offline_eligible INTEGER NOT NULL DEFAULT 0 CHECK (offline_eligible IN (0,1)),
  high_integrity_timed INTEGER NOT NULL DEFAULT 0 CHECK (high_integrity_timed IN (0,1)),
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_quiz_definitions_section ON quiz_definitions(site_id, section_id);

CREATE TABLE IF NOT EXISTS quiz_items (
  item_id TEXT PRIMARY KEY,
  quiz_id TEXT NOT NULL REFERENCES quiz_definitions(quiz_id),
  ordinal INTEGER NOT NULL,
  item_type TEXT NOT NULL CHECK (item_type IN (
    'single_choice','multi_select','true_false','short_response','numeric','file_response'
  )),
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]',
  max_points REAL NOT NULL DEFAULT 1,
  grading_mode TEXT NOT NULL DEFAULT 'objective' CHECK (grading_mode IN ('objective','manual')),
  UNIQUE(quiz_id, ordinal),
  CHECK (max_points >= 0)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
  attempt_id TEXT PRIMARY KEY,
  quiz_id TEXT NOT NULL REFERENCES quiz_definitions(quiz_id),
  learner_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  attempt_number INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  deadline_at TEXT,
  effective_time_limit_minutes REAL,
  submitted_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('in_progress','submitted','graded','returned','timed_out')),
  score REAL,
  max_score REAL,
  server_timed_out INTEGER NOT NULL DEFAULT 0 CHECK (server_timed_out IN (0,1)),
  accommodation_json TEXT,
  client_mutation_id TEXT,
  UNIQUE(quiz_id, learner_id, attempt_number),
  CHECK (attempt_number > 0)
);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_section ON quiz_attempts(section_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_quiz_attempts_mutation
  ON quiz_attempts(learner_id, client_mutation_id) WHERE client_mutation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS quiz_responses (
  response_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES quiz_attempts(attempt_id),
  item_id TEXT NOT NULL REFERENCES quiz_items(item_id),
  response_json TEXT NOT NULL,
  points_earned REAL,
  auto_graded INTEGER NOT NULL DEFAULT 0 CHECK (auto_graded IN (0,1)),
  manual_graded INTEGER NOT NULL DEFAULT 0 CHECK (manual_graded IN (0,1)),
  graded_by TEXT,
  graded_at TEXT,
  manual_comment TEXT,
  UNIQUE(attempt_id, item_id)
);

CREATE TABLE IF NOT EXISTS lab_definitions (
  lab_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  title TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN (
    'LOCAL_SOFTWARE','REPO_CONNECTED','DEVICE_HARDWARE_ASSISTED','MANUAL_EVIDENCE'
  )),
  spec_json TEXT NOT NULL,
  runner_id TEXT,
  offline_eligible INTEGER NOT NULL DEFAULT 0 CHECK (offline_eligible IN (0,1)),
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lab_definitions_section ON lab_definitions(site_id, section_id);

CREATE TABLE IF NOT EXISTS lab_runs (
  run_id TEXT PRIMARY KEY,
  lab_id TEXT NOT NULL REFERENCES lab_definitions(lab_id),
  learner_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  status TEXT NOT NULL CHECK (status IN ('completed','failed','timed_out','rejected')),
  evidence_json TEXT NOT NULL DEFAULT '{}',
  computed_evidence_json TEXT NOT NULL DEFAULT '{}',
  evidence_source TEXT NOT NULL DEFAULT 'learner_reported'
    CHECK (evidence_source IN ('server_computed','learner_reported','external_attested')),
  artifact_hashes_json TEXT NOT NULL DEFAULT '[]',
  runner_id TEXT,
  runner_exit_code INTEGER,
  runner_duration_ms INTEGER,
  runner_truncated INTEGER NOT NULL DEFAULT 0 CHECK (runner_truncated IN (0,1)),
  hardware_evidence_fabricated INTEGER NOT NULL DEFAULT 0 CHECK (hardware_evidence_fabricated IN (0,1)),
  started_at TEXT NOT NULL,
  completed_at TEXT,
  client_mutation_id TEXT,
  UNIQUE(lab_id, learner_id, client_mutation_id)
);
CREATE INDEX IF NOT EXISTS idx_lab_runs_section ON lab_runs(section_id, learner_id);

CREATE TABLE IF NOT EXISTS discussion_threads (
  thread_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  title TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  moderated INTEGER NOT NULL DEFAULT 0 CHECK (moderated IN (0,1)),
  locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_discussion_threads_section ON discussion_threads(site_id, section_id);

CREATE TABLE IF NOT EXISTS discussion_posts (
  post_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES discussion_threads(thread_id),
  parent_post_id TEXT REFERENCES discussion_posts(post_id),
  author_id TEXT NOT NULL REFERENCES users(user_id),
  body TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0,1)),
  moderation_note TEXT,
  moderated_by TEXT,
  CHECK (revision > 0)
);
CREATE INDEX IF NOT EXISTS idx_discussion_posts_thread ON discussion_posts(thread_id);

CREATE TABLE IF NOT EXISTS groups (
  group_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  name TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  UNIQUE(section_id, name)
);

CREATE TABLE IF NOT EXISTS group_members (
  group_id TEXT NOT NULL REFERENCES groups(group_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member','lead')),
  joined_at TEXT NOT NULL,
  PRIMARY KEY (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);

CREATE TABLE IF NOT EXISTS group_submissions (
  group_submission_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(group_id),
  activity_id TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  submitted_by TEXT NOT NULL REFERENCES users(user_id),
  contributions_json TEXT NOT NULL DEFAULT '[]',
  submitted_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  CHECK (length(content_hash) = 64)
);

CREATE TABLE IF NOT EXISTS accommodations (
  accommodation_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  time_multiplier REAL CHECK (time_multiplier IS NULL OR time_multiplier > 0),
  availability_extension_minutes INTEGER
    CHECK (availability_extension_minutes IS NULL OR availability_extension_minutes >= 0),
  attempt_override INTEGER CHECK (attempt_override IS NULL OR attempt_override > 0),
  due_extension_minutes INTEGER CHECK (due_extension_minutes IS NULL OR due_extension_minutes >= 0),
  alternate_modality TEXT,
  notes_private TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  UNIQUE(learner_id, section_id)
);

CREATE TABLE IF NOT EXISTS reusable_comments (
  comment_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT REFERENCES sections(section_id),
  author_id TEXT NOT NULL REFERENCES users(user_id),
  body TEXT NOT NULL,
  criterion_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regrade_queue (
  regrade_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  section_id TEXT REFERENCES sections(section_id),
  site_id TEXT REFERENCES sites(site_id),
  requested_by TEXT NOT NULL REFERENCES users(user_id),
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','in_progress','resolved','cancelled')),
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_regrade_queue_section ON regrade_queue(section_id, status);

CREATE TABLE IF NOT EXISTS grading_batches (
  batch_id TEXT PRIMARY KEY,
  instructor_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  criterion_id TEXT NOT NULL,
  points REAL NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  applied_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  CHECK (applied_count >= 0)
);
"""
