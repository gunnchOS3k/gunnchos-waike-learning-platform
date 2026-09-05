"""Gate A: offline leases, sync mutations/receipts, activity engine tables."""

SQL = """
CREATE TABLE IF NOT EXISTS offline_leases (
  lease_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  revoke_reason TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (site_id) REFERENCES sites(site_id),
  FOREIGN KEY (section_id) REFERENCES sections(section_id)
);
CREATE INDEX IF NOT EXISTS idx_offline_leases_user ON offline_leases(user_id, section_id);

CREATE TABLE IF NOT EXISTS sync_mutations (
  client_mutation_id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL DEFAULT 0,
  operation TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  local_sequence INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sync_status TEXT NOT NULL,
  server_revision INTEGER,
  result_json TEXT,
  acknowledged_at TEXT,
  UNIQUE(actor_id, client_mutation_id)
);
CREATE INDEX IF NOT EXISTS idx_sync_mutations_entity ON sync_mutations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_sync_mutations_status ON sync_mutations(sync_status);

CREATE TABLE IF NOT EXISTS sync_receipts (
  receipt_id TEXT PRIMARY KEY,
  client_mutation_id TEXT NOT NULL UNIQUE,
  actor_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  authoritative_revision INTEGER NOT NULL,
  result TEXT NOT NULL,
  payload_hash TEXT,
  server_timestamp TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entity_revisions (
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  actor_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (entity_type, entity_id, revision)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
  progress_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  pack_id TEXT NOT NULL,
  lesson_id TEXT NOT NULL,
  path TEXT NOT NULL DEFAULT '',
  scroll_offset REAL NOT NULL DEFAULT 0,
  percent_complete REAL NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, section_id, pack_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS draft_versions (
  version_id TEXT PRIMARY KEY,
  draft_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(draft_key, revision)
);

CREATE TABLE IF NOT EXISTS attachment_blobs (
  blob_id TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL UNIQUE,
  filename TEXT NOT NULL,
  safe_filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  storage_path TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0,
  quarantine_reason TEXT,
  uploaded_by TEXT NOT NULL,
  site_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_definitions (
  quiz_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  title TEXT NOT NULL,
  policies_json TEXT NOT NULL,
  answer_key_json TEXT NOT NULL,
  offline_eligible INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS quiz_items (
  item_id TEXT PRIMARY KEY,
  quiz_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  item_type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]',
  max_points REAL NOT NULL DEFAULT 1,
  grading_mode TEXT NOT NULL DEFAULT 'objective',
  FOREIGN KEY (quiz_id) REFERENCES quiz_definitions(quiz_id)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
  attempt_id TEXT PRIMARY KEY,
  quiz_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  submitted_at TEXT,
  status TEXT NOT NULL,
  score REAL,
  max_score REAL,
  server_timed_out INTEGER NOT NULL DEFAULT 0,
  accommodation_json TEXT,
  client_mutation_id TEXT,
  UNIQUE(quiz_id, learner_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS quiz_responses (
  response_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  response_json TEXT NOT NULL,
  points_earned REAL,
  auto_graded INTEGER NOT NULL DEFAULT 0,
  UNIQUE(attempt_id, item_id)
);

CREATE TABLE IF NOT EXISTS lab_definitions (
  lab_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  title TEXT NOT NULL,
  mode TEXT NOT NULL,
  spec_json TEXT NOT NULL,
  offline_eligible INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lab_runs (
  run_id TEXT PRIMARY KEY,
  lab_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  artifact_hashes_json TEXT NOT NULL DEFAULT '[]',
  hardware_evidence_fabricated INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  client_mutation_id TEXT,
  UNIQUE(lab_id, learner_id, client_mutation_id)
);

CREATE TABLE IF NOT EXISTS discussion_threads (
  thread_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  title TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  moderated INTEGER NOT NULL DEFAULT 0,
  locked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS discussion_posts (
  post_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  parent_post_id TEXT,
  author_id TEXT NOT NULL,
  body TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  moderation_note TEXT
);

CREATE TABLE IF NOT EXISTS groups (
  group_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
  group_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  joined_at TEXT NOT NULL,
  PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS group_submissions (
  group_submission_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  activity_id TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  submitted_by TEXT NOT NULL,
  contributions_json TEXT NOT NULL DEFAULT '[]',
  submitted_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS accommodations (
  accommodation_id TEXT PRIMARY KEY,
  learner_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  time_multiplier REAL,
  availability_extension_minutes INTEGER,
  attempt_override INTEGER,
  due_extension_minutes INTEGER,
  alternate_modality TEXT,
  notes_private TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(learner_id, section_id)
);

CREATE TABLE IF NOT EXISTS reusable_comments (
  comment_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  section_id TEXT,
  author_id TEXT NOT NULL,
  body TEXT NOT NULL,
  criterion_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regrade_queue (
  regrade_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS grading_batches (
  batch_id TEXT PRIMARY KEY,
  instructor_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  criterion_id TEXT NOT NULL,
  points REAL NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  applied_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
"""
