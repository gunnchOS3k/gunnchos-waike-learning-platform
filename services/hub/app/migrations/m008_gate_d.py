"""Gate D: guardian role + guardian–learner links.

SQLite cannot ALTER CHECK constraints — rebuild role_assignments / actors allowlists.
Forward-only. Does not weaken PR1–Gate C guarantees.
"""

SQL = """
CREATE TABLE IF NOT EXISTS guardian_links (
  link_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  guardian_user_id TEXT NOT NULL REFERENCES users(user_id),
  learner_user_id TEXT NOT NULL REFERENCES users(user_id),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL,
  UNIQUE(site_id, guardian_user_id, learner_user_id)
);
CREATE INDEX IF NOT EXISTS idx_guardian_links_guardian
  ON guardian_links(site_id, guardian_user_id, active);
CREATE INDEX IF NOT EXISTS idx_guardian_links_learner
  ON guardian_links(site_id, learner_user_id, active);

-- Expand role allowlist to include guardian (rebuild tables).
CREATE TABLE IF NOT EXISTS role_assignments_gate_d (
  assignment_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  role TEXT NOT NULL CHECK(role IN ('learner','instructor','grader','guardian','site_admin')),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, site_id, role)
);
INSERT OR IGNORE INTO role_assignments_gate_d
  SELECT assignment_id, user_id, site_id, role, active, created_at FROM role_assignments;
DROP TABLE role_assignments;
ALTER TABLE role_assignments_gate_d RENAME TO role_assignments;

CREATE TABLE IF NOT EXISTS actors_gate_d (
  actor_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK(role IN ('learner','instructor','grader','guardian','site_admin')),
  display_name TEXT NOT NULL
);
INSERT OR IGNORE INTO actors_gate_d SELECT actor_id, role, display_name FROM actors;
DROP TABLE actors;
ALTER TABLE actors_gate_d RENAME TO actors;
"""
