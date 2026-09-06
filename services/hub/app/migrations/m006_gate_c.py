"""Gate C: interoperability (OneRoster/QTI/LTI), Device OS bridge metadata, hardening.

Forward-only. Does not weaken PR1–Gate B guarantees.
"""

SQL = """
CREATE TABLE IF NOT EXISTS oneroster_imports (
  import_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  source_filename TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  created_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  report_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oneroster_imports_site ON oneroster_imports(site_id, created_at);

CREATE TABLE IF NOT EXISTS oneroster_entities (
  entity_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  entity_type TEXT NOT NULL CHECK (entity_type IN (
    'org','user','course','class','enrollment'
  )),
  sourced_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  payload_json TEXT NOT NULL DEFAULT '{}',
  local_ref TEXT,
  date_last_modified TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(site_id, entity_type, sourced_id)
);
CREATE INDEX IF NOT EXISTS idx_oneroster_entities_type ON oneroster_entities(site_id, entity_type);

CREATE TABLE IF NOT EXISTS qti_imports (
  import_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  section_id TEXT REFERENCES sections(section_id),
  quiz_id TEXT,
  source_sha256 TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  report_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lti_registrations (
  registration_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  issuer TEXT NOT NULL,
  client_id TEXT NOT NULL,
  deployment_id TEXT NOT NULL,
  auth_login_url TEXT NOT NULL,
  auth_token_url TEXT NOT NULL,
  jwks_url TEXT NOT NULL,
  target_link_uri TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL,
  UNIQUE(site_id, issuer, client_id, deployment_id)
);

CREATE TABLE IF NOT EXISTS lti_nonces (
  nonce TEXT PRIMARY KEY,
  registration_id TEXT NOT NULL REFERENCES lti_registrations(registration_id),
  used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lti_states (
  state TEXT PRIMARY KEY,
  registration_id TEXT NOT NULL REFERENCES lti_registrations(registration_id),
  nonce TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS lti_launches (
  launch_id TEXT PRIMARY KEY,
  registration_id TEXT NOT NULL REFERENCES lti_registrations(registration_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  mapped_user_id TEXT,
  mapped_role TEXT,
  subject TEXT NOT NULL,
  target_link_uri TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_capability_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  capabilities_json TEXT NOT NULL,
  discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS continuity_handoffs (
  handoff_id TEXT PRIMARY KEY,
  from_profile TEXT NOT NULL,
  to_profile TEXT NOT NULL,
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backup_manifests (
  backup_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  manifest_sha256 TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  bucket_key TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  window_start TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS privacy_controls (
  control_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  youth_mode INTEGER NOT NULL DEFAULT 0 CHECK (youth_mode IN (0,1)),
  data_minimization INTEGER NOT NULL DEFAULT 1 CHECK (data_minimization IN (0,1)),
  export_allowed INTEGER NOT NULL DEFAULT 0 CHECK (export_allowed IN (0,1)),
  retention_days INTEGER NOT NULL DEFAULT 365,
  matrix_json TEXT NOT NULL DEFAULT '{}',
  updated_by TEXT NOT NULL REFERENCES users(user_id),
  updated_at TEXT NOT NULL,
  UNIQUE(site_id)
);

CREATE TABLE IF NOT EXISTS package_lifecycle_events (
  event_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL,
  package_version TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN (
    'install','upgrade','downgrade_blocked','revoke','deprecate','rollback'
  )),
  detail_json TEXT NOT NULL DEFAULT '{}',
  actor_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_audit (
  event_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  action TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observability_events (
  event_id TEXT PRIMARY KEY,
  level TEXT NOT NULL CHECK (level IN ('debug','info','warn','error')),
  category TEXT NOT NULL,
  message TEXT NOT NULL,
  redacted_detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""
