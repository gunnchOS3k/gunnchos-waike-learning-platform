"""Gate B: server-authoritative AI policy + AI audit (gunnchAI integration).

Forward-only. Policies attach to section / assessment / activity scopes.
Learners cannot write these rows; only instructor-side actors may set policy.
"""

SQL = """
CREATE TABLE IF NOT EXISTS ai_policies (
  policy_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  scope TEXT NOT NULL CHECK (scope IN ('section','assessment','activity')),
  section_id TEXT NOT NULL REFERENCES sections(section_id),
  assessment_id TEXT,
  activity_id TEXT,
  policy TEXT NOT NULL CHECK (policy IN (
    'AI_ALLOWED','AI_HINTS_ONLY','AI_DISABLED','AI_INSTRUCTOR_DEFINED'
  )),
  instructor_defined_json TEXT NOT NULL DEFAULT '{}',
  set_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (
    (scope = 'section' AND assessment_id IS NULL AND activity_id IS NULL)
    OR (scope = 'assessment' AND assessment_id IS NOT NULL AND activity_id IS NULL)
    OR (scope = 'activity' AND activity_id IS NOT NULL)
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_policies_section_only
  ON ai_policies(section_id) WHERE scope = 'section';
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_policies_assessment
  ON ai_policies(section_id, assessment_id) WHERE scope = 'assessment';
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_policies_activity
  ON ai_policies(section_id, activity_id) WHERE scope = 'activity';
CREATE INDEX IF NOT EXISTS idx_ai_policies_site ON ai_policies(site_id, section_id);

CREATE TABLE IF NOT EXISTS ai_cloud_consent (
  consent_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  cloud_permitted INTEGER NOT NULL DEFAULT 0 CHECK (cloud_permitted IN (0,1)),
  granted_at TEXT,
  revoked_at TEXT,
  UNIQUE(user_id, site_id)
);

CREATE TABLE IF NOT EXISTS ai_assist_audit (
  event_id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL REFERENCES users(user_id),
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  section_id TEXT REFERENCES sections(section_id),
  mode TEXT NOT NULL,
  capability TEXT NOT NULL,
  policy TEXT,
  allowed INTEGER NOT NULL CHECK (allowed IN (0,1)),
  refusal_code TEXT,
  query_hash TEXT NOT NULL,
  provider_id TEXT,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_assist_audit_actor ON ai_assist_audit(actor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_assist_audit_section ON ai_assist_audit(section_id, created_at);
"""
