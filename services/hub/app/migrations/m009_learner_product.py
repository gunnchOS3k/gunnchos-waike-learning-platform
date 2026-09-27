"""Learner-first product tables. Additive. Does not rewrite assessment/identity."""

SQL = """
CREATE TABLE IF NOT EXISTS comment_bank (
  comment_id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comment_bank_owner ON comment_bank(owner_user_id, site_id);

CREATE TABLE IF NOT EXISTS school_apps (
  app_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  label TEXT NOT NULL,
  launch_kind TEXT NOT NULL CHECK(launch_kind IN ('web','lti','browser_url')),
  url TEXT NOT NULL,
  allowed_origins_json TEXT NOT NULL,
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_notification_reads (
  read_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  notice_id TEXT NOT NULL,
  read_at TEXT NOT NULL,
  UNIQUE(user_id, notice_id)
);

CREATE TABLE IF NOT EXISTS due_shift_events (
  event_id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  delta_hours INTEGER NOT NULL,
  preview_json TEXT NOT NULL,
  applied INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
"""
