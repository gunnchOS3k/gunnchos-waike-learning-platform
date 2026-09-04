"""003 — Identity, sites, sections, enrollment, gradebook (PR3). Forward-only."""

SQL = """
CREATE TABLE IF NOT EXISTS sites (
  site_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  username TEXT NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(site_id, username)
);

CREATE TABLE IF NOT EXISTS role_assignments (
  assignment_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  role TEXT NOT NULL CHECK(role IN ('learner','instructor','grader','site_admin')),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, site_id, role)
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS packages (
  package_id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL,
  title TEXT NOT NULL,
  source_commit TEXT NOT NULL DEFAULT '',
  immutable INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
  section_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  package_id TEXT NOT NULL REFERENCES packages(package_id),
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(site_id, code)
);

CREATE TABLE IF NOT EXISTS section_runtime_metadata (
  section_id TEXT PRIMARY KEY REFERENCES sections(section_id),
  due_override_json TEXT NOT NULL DEFAULT '{}',
  publish_notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS section_instructors (
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  assigned_at TEXT NOT NULL,
  PRIMARY KEY (section_id, user_id)
);

CREATE TABLE IF NOT EXISTS section_graders (
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  assigned_at TEXT NOT NULL,
  PRIMARY KEY (section_id, user_id)
);

CREATE TABLE IF NOT EXISTS enrollments (
  enrollment_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  status TEXT NOT NULL CHECK(status IN ('active','inactive','withdrawn')),
  enrolled_at TEXT NOT NULL,
  deactivated_at TEXT
);

-- At most one active enrollment per (section, user)
CREATE UNIQUE INDEX IF NOT EXISTS enrollments_one_active
  ON enrollments(section_id, user_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS gradebook_categories (
  category_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  name TEXT NOT NULL,
  weight REAL NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  CHECK(weight >= 0)
);

CREATE TABLE IF NOT EXISTS gradebook_items (
  item_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  category_id TEXT NOT NULL REFERENCES gradebook_categories(category_id),
  assignment_id TEXT,
  title TEXT NOT NULL,
  points_possible REAL NOT NULL,
  due_at TEXT,
  created_at TEXT NOT NULL,
  CHECK(points_possible > 0)
);

CREATE TABLE IF NOT EXISTS gradebook_policies (
  section_id TEXT PRIMARY KEY REFERENCES sections(section_id),
  late_penalty_pct REAL NOT NULL DEFAULT 0,
  drop_lowest INTEGER NOT NULL DEFAULT 0,
  missing_as_zero INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gradebook_score_entries (
  entry_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES gradebook_items(item_id),
  learner_id TEXT NOT NULL REFERENCES users(user_id),
  points_earned REAL,
  status TEXT NOT NULL CHECK(status IN ('graded','ungraded','missing','late','excused')),
  graded_by TEXT,
  graded_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(item_id, learner_id)
);

CREATE TABLE IF NOT EXISTS grade_override_audits (
  override_id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES gradebook_score_entries(entry_id),
  actor_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Scope assessment rows to sections (nullable until backfill)
ALTER TABLE drafts ADD COLUMN section_id TEXT;
ALTER TABLE submissions ADD COLUMN section_id TEXT;
ALTER TABLE gradebook_entries ADD COLUMN section_id TEXT;
ALTER TABLE grades ADD COLUMN section_id TEXT;

CREATE INDEX IF NOT EXISTS idx_submissions_section ON submissions(section_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_user ON enrollments(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
"""
