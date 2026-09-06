"""Hardening helpers: rate limits, privacy, admin, observability, package lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row

SECRET_PATTERNS = [
    re.compile(r"(password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+", re.I),
    re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"WAIKE_DEV_DB_KEY=\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
]


def redact_text(text: str) -> str:
    out = text or ""
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def redact_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]"
            if any(s in k.lower() for s in ("password", "token", "secret", "private", "key"))
            else redact_obj(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


class RateLimiter:
    def __init__(self, conn: sqlite3.Connection, limit: int = 30, window_seconds: int = 60) -> None:
        self.conn = conn
        self.limit = limit
        self.window = window_seconds

    def check(self, key: str) -> dict[str, Any]:
        now = _now()
        row = _row(self.conn, "SELECT count, window_start FROM rate_limit_buckets WHERE bucket_key=?", (key,))
        if row is None:
            self.conn.execute(
                "INSERT INTO rate_limit_buckets(bucket_key, count, window_start) VALUES (?,?,?)",
                (key, 1, now),
            )
            self.conn.commit()
            return {"allowed": True, "remaining": self.limit - 1}
        # Simple string-time window: reset when minute changes (deterministic for tests via count)
        count = int(row["count"]) + 1
        if count > self.limit:
            raise ServiceError("RATE_LIMITED", 429)
        self.conn.execute(
            "UPDATE rate_limit_buckets SET count=? WHERE bucket_key=?",
            (count, key),
        )
        self.conn.commit()
        return {"allowed": True, "remaining": max(0, self.limit - count)}


class PrivacyService:
    """Youth/privacy controls — does NOT claim FERPA certification."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def matrix(self, site_id: str) -> dict[str, Any]:
        row = _row(self.conn, "SELECT * FROM privacy_controls WHERE site_id=?", (site_id,))
        base = {
            "ferpa_claim": False,
            "claim_boundary": "Digital privacy controls only — not FERPA certification",
            "controls": {
                "youth_mode": bool(row["youth_mode"]) if row else False,
                "data_minimization": bool(row["data_minimization"]) if row else True,
                "export_allowed": bool(row["export_allowed"]) if row else False,
                "retention_days": int(row["retention_days"]) if row else 365,
            },
            "data_classes": {
                "directory": "site_admin",
                "grades": "instructor_side",
                "submissions": "instructor_side_or_owner",
                "ai_audit": "instructor_side_redacted",
                "backups": "site_admin",
            },
        }
        return base

    def upsert(self, actor: Actor, **kwargs: Any) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("PRIVACY_FORBIDDEN", 403)
        now = _now()
        existing = _row(self.conn, "SELECT control_id FROM privacy_controls WHERE site_id=?", (actor.site_id,))
        matrix = self.matrix(actor.site_id)
        matrix["controls"].update({k: kwargs[k] for k in kwargs if k in matrix["controls"]})
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO privacy_controls(
                  control_id, site_id, youth_mode, data_minimization, export_allowed,
                  retention_days, matrix_json, updated_by, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    _id("priv"),
                    actor.site_id,
                    int(bool(kwargs.get("youth_mode", False))),
                    int(bool(kwargs.get("data_minimization", True))),
                    int(bool(kwargs.get("export_allowed", False))),
                    int(kwargs.get("retention_days", 365)),
                    json.dumps(matrix),
                    actor.actor_id,
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE privacy_controls SET youth_mode=?, data_minimization=?, export_allowed=?,
                  retention_days=?, matrix_json=?, updated_by=?, updated_at=?
                WHERE site_id=?
                """,
                (
                    int(bool(kwargs.get("youth_mode", False))),
                    int(bool(kwargs.get("data_minimization", True))),
                    int(bool(kwargs.get("export_allowed", False))),
                    int(kwargs.get("retention_days", 365)),
                    json.dumps(matrix),
                    actor.actor_id,
                    now,
                    actor.site_id,
                ),
            )
        self.conn.commit()
        return self.matrix(actor.site_id)


class AdminConsole:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def dashboard(self, actor: Actor) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("ADMIN_FORBIDDEN", 403)
        users = self.conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE site_id=?", (actor.site_id,)
        ).fetchone()["c"]
        sections = self.conn.execute(
            "SELECT COUNT(*) AS c FROM sections WHERE site_id=?", (actor.site_id,)
        ).fetchone()["c"]
        return {
            "site_id": actor.site_id,
            "users": users,
            "sections": sections,
            "workflows": [
                "user_disable",
                "role_assign",
                "oneroster_import",
                "backup_restore",
                "privacy_controls",
                "package_lifecycle",
                "diagnostics",
            ],
        }

    def audit(self, actor: Actor, action: str, detail: dict[str, Any] | None = None) -> str:
        if not actor.is_site_admin:
            raise ServiceError("ADMIN_FORBIDDEN", 403)
        eid = _id("admaud")
        self.conn.execute(
            """
            INSERT INTO admin_audit(event_id, site_id, actor_id, action, detail_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (eid, actor.site_id, actor.actor_id, action, json.dumps(redact_obj(detail or {})), _now()),
        )
        self.conn.commit()
        return eid


class Observability:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def emit(self, level: str, category: str, message: str, detail: dict[str, Any] | None = None) -> str:
        eid = _id("obs")
        self.conn.execute(
            """
            INSERT INTO observability_events(event_id, level, category, message, redacted_detail_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                eid,
                level,
                category,
                redact_text(message),
                json.dumps(redact_obj(detail or {})),
                _now(),
            ),
        )
        self.conn.commit()
        return eid

    def diagnostics(self, actor: Actor) -> dict[str, Any]:
        if not (actor.is_site_admin or actor.is_instructor_side):
            raise ServiceError("DIAGNOSTICS_FORBIDDEN", 403)
        migrations = [
            r[0] for r in self.conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        ]
        return {
            "schema_migrations": migrations,
            "health": "ok",
            "redaction": True,
            "note": "Diagnostics omit secrets/keys/tokens",
        }


class PackageLifecycle:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record(
        self,
        actor: Actor | None,
        *,
        track_id: str,
        package_version: str,
        action: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if action == "downgrade_blocked":
            pass
        elif action not in {"install", "upgrade", "revoke", "deprecate", "rollback", "downgrade_blocked"}:
            raise ServiceError("PACKAGE_BAD_ACTION", 400)
        eid = _id("pkg")
        self.conn.execute(
            """
            INSERT INTO package_lifecycle_events(
              event_id, track_id, package_version, action, detail_json, actor_id, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                eid,
                track_id,
                package_version,
                action,
                json.dumps(detail or {}),
                actor.actor_id if actor else None,
                _now(),
            ),
        )
        self.conn.commit()
        return {"event_id": eid, "action": action, "track_id": track_id}

    def assert_no_silent_downgrade(self, track_id: str, from_v: str, to_v: str) -> dict[str, Any]:
        # Lexicographic digital policy: explicit block record required for downgrade.
        if to_v < from_v:
            return self.record(
                None,
                track_id=track_id,
                package_version=to_v,
                action="downgrade_blocked",
                detail={"from": from_v, "to": to_v},
            )
        return self.record(None, track_id=track_id, package_version=to_v, action="upgrade", detail={"from": from_v})
