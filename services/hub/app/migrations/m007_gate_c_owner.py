"""Gate C owner closure: QTI external ids, LTI identities, package states, backup hashes.

Forward-only. Does not weaken PR1–Gate B or m006 guarantees.
"""

SQL = """
ALTER TABLE quiz_items ADD COLUMN external_identifier TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_quiz_items_external
  ON quiz_items(quiz_id, external_identifier)
  WHERE external_identifier IS NOT NULL;

CREATE TABLE IF NOT EXISTS lti_external_identities (
  identity_id TEXT PRIMARY KEY,
  registration_id TEXT NOT NULL REFERENCES lti_registrations(registration_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  subject TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  UNIQUE(registration_id, subject)
);
CREATE INDEX IF NOT EXISTS idx_lti_ext_ident_subject
  ON lti_external_identities(site_id, subject);

CREATE TABLE IF NOT EXISTS package_states (
  track_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN (
    'none','installed','active','deprecated','revoked','archived','incompatible'
  )),
  package_version TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS backup_member_hashes (
  backup_id TEXT NOT NULL REFERENCES backup_manifests(backup_id),
  member_name TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  PRIMARY KEY (backup_id, member_name)
);

CREATE TABLE IF NOT EXISTS retention_operations (
  operation_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  action TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""
