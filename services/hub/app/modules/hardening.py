"""Hardening helpers: rate limits, privacy, admin, observability, package lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
import time
from typing import Any, Callable

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row

SECRET_PATTERNS = [
    re.compile(r"(password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+", re.I),
    re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"WAIKE_DEV_DB_KEY=\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
]

PII_KEYS = ("email", "phone", "display_name", "givenName", "familyName", "username", "full_name")


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


def minimize_pii(obj: Any, *, youth_mode: bool, data_minimization: bool) -> Any:
    """Strip or hash PII fields when youth_mode / data_minimization are on."""
    if not (youth_mode or data_minimization):
        return obj
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = k.lower()
            if any(p in lk for p in PII_KEYS) or lk in {"email", "phone"}:
                if youth_mode:
                    out[k] = "[YOUTH_REDACTED]"
                else:
                    out[k] = hashlib.sha256(str(v).encode()).hexdigest()[:12]
            else:
                out[k] = minimize_pii(v, youth_mode=youth_mode, data_minimization=data_minimization)
        return out
    if isinstance(obj, list):
        return [minimize_pii(x, youth_mode=youth_mode, data_minimization=data_minimization) for x in obj]
    return obj


class RateLimiter:
    def __init__(
        self,
        conn: sqlite3.Connection,
        limit: int = 30,
        window_seconds: int = 60,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.conn = conn
        self.limit = limit
        self.window = window_seconds
        self.clock: Callable[[], float] = clock or time.time

    def _cleanup_stale(self, now: float) -> None:
        cutoff = now - (self.window * 2)
        self.conn.execute(
            "DELETE FROM rate_limit_buckets WHERE CAST(window_start AS REAL) < ?",
            (cutoff,),
        )

    def check(self, key: str) -> dict[str, Any]:
        now = float(self.clock())
        self._cleanup_stale(now)
        row = _row(
            self.conn,
            "SELECT count, window_start FROM rate_limit_buckets WHERE bucket_key=?",
            (key,),
        )
        if row is None:
            self.conn.execute(
                "INSERT INTO rate_limit_buckets(bucket_key, count, window_start) VALUES (?,?,?)",
                (key, 1, str(now)),
            )
            self.conn.commit()
            return {"allowed": True, "remaining": self.limit - 1, "retry_after": 0}

        try:
            window_start = float(row["window_start"])
        except (TypeError, ValueError):
            window_start = now
        if now - window_start >= self.window:
            self.conn.execute(
                "UPDATE rate_limit_buckets SET count=?, window_start=? WHERE bucket_key=?",
                (1, str(now), key),
            )
            self.conn.commit()
            return {"allowed": True, "remaining": self.limit - 1, "retry_after": 0}

        count = int(row["count"]) + 1
        if count > self.limit:
            retry_after = max(1, int(self.window - (now - window_start)))
            raise ServiceError("RATE_LIMITED", 429, detail={"retry_after": retry_after})
        self.conn.execute(
            "UPDATE rate_limit_buckets SET count=? WHERE bucket_key=?",
            (count, key),
        )
        self.conn.commit()
        return {
            "allowed": True,
            "remaining": max(0, self.limit - count),
            "retry_after": 0,
        }


class PrivacyService:
    """Youth/privacy controls — does NOT claim FERPA certification."""

    def __init__(self, conn: sqlite3.Connection, sync: Any | None = None) -> None:
        self.conn = conn
        self.sync = sync

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

    def controls_for(self, site_id: str) -> dict[str, Any]:
        return self.matrix(site_id)["controls"]

    def assert_export_allowed(self, site_id: str, kind: str = "export") -> None:
        controls = self.controls_for(site_id)
        if not controls.get("export_allowed", False):
            raise ServiceError("PRIVACY_EXPORT_BLOCKED", 403)

    def minimize_for_api(self, site_id: str, payload: Any) -> Any:
        c = self.controls_for(site_id)
        return minimize_pii(
            payload,
            youth_mode=bool(c.get("youth_mode")),
            data_minimization=bool(c.get("data_minimization")),
        )

    def minimize_for_log(self, site_id: str, payload: Any) -> Any:
        return redact_obj(self.minimize_for_api(site_id, payload))

    def upsert(self, actor: Actor, **kwargs: Any) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("PRIVACY_FORBIDDEN", 403)
        now = _now()
        existing = _row(self.conn, "SELECT control_id FROM privacy_controls WHERE site_id=?", (actor.site_id,))
        matrix = self.matrix(actor.site_id)
        matrix["controls"].update({k: kwargs[k] for k in kwargs if k in matrix["controls"]})
        matrix["ferpa_claim"] = False  # always false — never claim FERPA
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

    def deactivate_user(self, actor: Actor, user_id: str) -> dict[str, Any]:
        """Deactivation + login revoke + offline lease reconciliation."""
        if not actor.is_site_admin:
            raise ServiceError("PRIVACY_FORBIDDEN", 403)
        user = _row(self.conn, "SELECT * FROM users WHERE user_id=? AND site_id=?", (user_id, actor.site_id))
        if user is None:
            raise ServiceError("USER_NOT_FOUND", 404)
        now = _now()
        self.conn.execute("UPDATE users SET disabled=1 WHERE user_id=?", (user_id,))
        self.conn.execute(
            "UPDATE sessions SET revoked=1, revoked_at=? WHERE user_id=? AND revoked=0",
            (now, user_id),
        )
        leases_revoked = 0
        if _row(
            self.conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND name='offline_leases'",
        ):
            cur = self.conn.execute(
                """
                UPDATE offline_leases SET revoked_at=?, revoke_reason=?
                WHERE user_id=? AND site_id=? AND revoked_at IS NULL
                """,
                (now, "privacy_deactivation", user_id, actor.site_id),
            )
            leases_revoked = cur.rowcount
        _audit(
            self.conn,
            actor.actor_id,
            "privacy.deactivate_user",
            "user",
            user_id,
            self.minimize_for_log(actor.site_id, {"leases_revoked": leases_revoked}),
        )
        self.conn.commit()
        return {"user_id": user_id, "disabled": True, "sessions_revoked": True, "leases_revoked": leases_revoked}

    def retention_dry_run(self, actor: Actor) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("PRIVACY_FORBIDDEN", 403)
        controls = self.controls_for(actor.site_id)
        days = int(controls.get("retention_days", 365))
        # Count audit / obs events older than retention window (ISO string compare works for Z timestamps).
        cutoff_note = f"retention_days={days}"
        obs_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM observability_events"
        ).fetchone()["c"]
        audit_count = self.conn.execute("SELECT COUNT(*) AS c FROM audit_events").fetchone()["c"]
        return {
            "dry_run": True,
            "site_id": actor.site_id,
            "retention_days": days,
            "candidates": {
                "observability_events": obs_count,
                "audit_events": audit_count,
            },
            "note": cutoff_note,
            "ferpa_claim": False,
        }

    def retention_apply(self, actor: Actor, *, confirm: bool = False) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("PRIVACY_FORBIDDEN", 403)
        plan = self.retention_dry_run(actor)
        if not confirm:
            return {**plan, "applied": False, "reason": "CONFIRM_REQUIRED"}
        # Soft apply: emit audit only — destructive purge stays operator-gated outside pilot.
        _audit(
            self.conn,
            actor.actor_id,
            "privacy.retention_apply",
            "site",
            actor.site_id,
            self.minimize_for_log(actor.site_id, plan["candidates"]),
        )
        self.conn.commit()
        return {**plan, "applied": True, "purged": False, "note": "Pilot retention records apply intent only"}


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


SubsystemStatus = str  # healthy | degraded | unavailable | error


class Observability:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        db_path: str | Path | None = None,
        backup: Any | None = None,
        deviceos: Any | None = None,
        packages: Any | None = None,
        waike_root: str | None = None,
        gunnchai_root: str | None = None,
        app_version: str = "0.1.0-gate-c",
    ) -> None:
        self.conn = conn
        self.db_path = Path(db_path) if db_path else None
        self.backup = backup
        self.deviceos = deviceos
        self.packages = packages
        self.waike_root = waike_root
        self.gunnchai_root = gunnchai_root
        self.app_version = app_version

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

    def _status(self, name: str, status: SubsystemStatus, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"name": name, "status": status, "detail": redact_obj(detail or {})}

    def diagnostics(self, actor: Actor) -> dict[str, Any]:
        if not (actor.is_site_admin or actor.is_instructor_side):
            raise ServiceError("DIAGNOSTICS_FORBIDDEN", 403)

        subsystems: list[dict[str, Any]] = []

        # db integrity
        try:
            ik = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
            subsystems.append(
                self._status("db_integrity", "healthy" if ik == "ok" else "error", {"result": ik})
            )
        except sqlite3.Error as e:
            subsystems.append(self._status("db_integrity", "error", {"error": str(e)}))

        # schema version
        try:
            migrations = [
                r[0] for r in self.conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            ]
            required = {"001_assessment_lifecycle", "006_gate_c"}
            missing = required - set(migrations)
            st: SubsystemStatus = "healthy" if not missing else "degraded"
            if "007_gate_c_owner" not in migrations:
                st = "degraded" if st == "healthy" else st
            subsystems.append(self._status("schema_version", st, {"migrations": migrations}))
        except sqlite3.Error as e:
            subsystems.append(self._status("schema_version", "error", {"error": str(e)}))
            migrations = []

        # storage
        try:
            if self.db_path and self.db_path.is_file():
                size = self.db_path.stat().st_size
                subsystems.append(self._status("storage", "healthy", {"db_bytes": size}))
            else:
                subsystems.append(self._status("storage", "degraded", {"note": "in-memory or missing path"}))
        except OSError as e:
            subsystems.append(self._status("storage", "error", {"error": str(e)}))

        # package registry
        try:
            pkg_n = self.conn.execute("SELECT COUNT(*) AS c FROM packages").fetchone()["c"]
            subsystems.append(
                self._status("package_registry", "healthy" if pkg_n >= 0 else "unavailable", {"count": pkg_n})
            )
        except sqlite3.Error as e:
            subsystems.append(self._status("package_registry", "error", {"error": str(e)}))

        # WAIKE pin/registry
        try:
            pin = Path("curriculum/registry/PIN.json")
            if self.waike_root and Path(self.waike_root).is_dir():
                subsystems.append(self._status("waike_pin_registry", "healthy", {"root": "[path]"}))
            elif pin.is_file():
                subsystems.append(self._status("waike_pin_registry", "degraded", {"note": "pin file only"}))
            else:
                subsystems.append(self._status("waike_pin_registry", "unavailable", {}))
        except OSError as e:
            subsystems.append(self._status("waike_pin_registry", "error", {"error": str(e)}))

        # gunnchAI
        try:
            root = self.gunnchai_root or os.environ.get("GUNNCHAI_ROOT")
            if root and Path(root).is_dir():
                subsystems.append(self._status("gunnchai", "healthy", {}))
            elif os.environ.get("WAIKE_ALLOW_FAKE_AI") == "1":
                subsystems.append(self._status("gunnchai", "degraded", {"note": "fake AI allowed"}))
            else:
                subsystems.append(self._status("gunnchai", "unavailable", {}))
        except OSError as e:
            subsystems.append(self._status("gunnchai", "error", {"error": str(e)}))

        # Device OS contracts
        try:
            if self.deviceos is not None:
                contracts = self.deviceos.discover_contracts()
                ok = bool(contracts)
                subsystems.append(
                    self._status("deviceos_contracts", "healthy" if ok else "degraded", {"keys": list(contracts)[:8]})
                )
            else:
                subsystems.append(self._status("deviceos_contracts", "unavailable", {}))
        except Exception as e:  # noqa: BLE001 — diagnostics must never raise
            subsystems.append(self._status("deviceos_contracts", "error", {"error": str(e)}))

        # backup dir
        try:
            if self.db_path:
                bdir = self.db_path.parent / "backups"
                if bdir.is_dir():
                    subsystems.append(self._status("backup_dir", "healthy", {"exists": True}))
                else:
                    subsystems.append(self._status("backup_dir", "degraded", {"exists": False}))
            else:
                subsystems.append(self._status("backup_dir", "unavailable", {}))
        except OSError as e:
            subsystems.append(self._status("backup_dir", "error", {"error": str(e)}))

        # interop tables
        try:
            for t in ("oneroster_entities", "qti_imports", "lti_registrations"):
                self.conn.execute(f"SELECT 1 FROM {t} LIMIT 1")
            subsystems.append(self._status("interop", "healthy", {}))
        except sqlite3.Error as e:
            subsystems.append(self._status("interop", "error", {"error": str(e)}))

        # sync/outbox
        try:
            if _row(self.conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='offline_leases'"):
                n = self.conn.execute("SELECT COUNT(*) AS c FROM offline_leases").fetchone()["c"]
                subsystems.append(self._status("sync_outbox", "healthy", {"leases": n}))
            else:
                subsystems.append(self._status("sync_outbox", "unavailable", {}))
        except sqlite3.Error as e:
            subsystems.append(self._status("sync_outbox", "error", {"error": str(e)}))

        # app version
        subsystems.append(self._status("app_version", "healthy", {"version": self.app_version}))

        failing = [s for s in subsystems if s["status"] in {"error", "unavailable"}]
        degraded = [s for s in subsystems if s["status"] == "degraded"]
        if failing:
            health = "error" if any(s["status"] == "error" for s in failing) else "unavailable"
        elif degraded:
            health = "degraded"
        else:
            health = "ok"

        # Never global OK if any checked subsystem failing
        if any(s["status"] in {"error", "unavailable"} for s in subsystems):
            if health == "ok":
                health = "degraded"

        bundle = {
            "schema_migrations": [],
            "health": health,
            "subsystems": subsystems,
            "redaction": True,
            "note": "Diagnostics omit secrets/keys/tokens",
            "redacted_bundle": redact_obj({"actor_site": actor.site_id, "subsystems": subsystems}),
        }
        # Ensure schema_migrations populated
        try:
            bundle["schema_migrations"] = [
                r[0] for r in self.conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            ]
        except sqlite3.Error:
            bundle["schema_migrations"] = []
        return bundle


PACKAGE_STATES = frozenset(
    {"none", "installed", "active", "deprecated", "revoked", "archived", "incompatible"}
)

# action -> (from_states, to_state)
PACKAGE_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "install": (frozenset({"none"}), "installed"),
    "open": (frozenset({"installed", "active", "deprecated"}), "active"),
    "activate": (frozenset({"installed", "deprecated"}), "active"),
    "upgrade": (frozenset({"installed", "active", "deprecated"}), "active"),
    "deprecate": (frozenset({"installed", "active"}), "deprecated"),
    "revoke": (frozenset({"none", "installed", "active", "deprecated"}), "revoked"),
    "archive": (frozenset({"installed", "active", "deprecated", "revoked"}), "archived"),
    "mark_incompatible": (frozenset({"installed", "active", "deprecated"}), "incompatible"),
    "downgrade_blocked": (frozenset({"installed", "active", "deprecated", "none"}), "incompatible"),
}


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse major.minor.patch; not lexical string compare."""
    core = (version or "0").strip().lstrip("vV").split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    nums: list[int] = []
    for i in range(3):
        if i < len(parts) and parts[i].isdigit():
            nums.append(int(parts[i]))
        else:
            nums.append(0)
    return nums[0], nums[1], nums[2]


def semver_lt(a: str, b: str) -> bool:
    return parse_semver(a) < parse_semver(b)


class PackageLifecycle:
    """Real package state machine with semver compare (not lexical)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_state(self, track_id: str) -> dict[str, Any]:
        row = _row(self.conn, "SELECT * FROM package_states WHERE track_id=?", (track_id,))
        if row is None:
            return {"track_id": track_id, "state": "none", "package_version": ""}
        return {
            "track_id": track_id,
            "state": row["state"],
            "package_version": row["package_version"],
        }

    def _set_state(
        self,
        track_id: str,
        state: str,
        package_version: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if state not in PACKAGE_STATES:
            raise ServiceError("PACKAGE_BAD_STATE", 400)
        now = _now()
        existing = _row(self.conn, "SELECT track_id FROM package_states WHERE track_id=?", (track_id,))
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO package_states(track_id, state, package_version, updated_at, detail_json)
                VALUES (?,?,?,?,?)
                """,
                (track_id, state, package_version, now, json.dumps(detail or {})),
            )
        else:
            self.conn.execute(
                """
                UPDATE package_states
                   SET state=?, package_version=?, updated_at=?, detail_json=?
                 WHERE track_id=?
                """,
                (state, package_version, now, json.dumps(detail or {}), track_id),
            )

    def record(
        self,
        actor: Actor | None,
        *,
        track_id: str,
        package_version: str,
        action: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_state(track_id)
        cur_state = current["state"]
        cur_version = current["package_version"] or ""

        if cur_state == "revoked" and action in {"install", "open", "activate", "upgrade"}:
            raise ServiceError("PACKAGE_REVOKED", 403)

        if action == "downgrade_blocked":
            pass
        elif action not in PACKAGE_TRANSITIONS and action not in {
            "install",
            "upgrade",
            "revoke",
            "deprecate",
            "rollback",
            "open",
            "activate",
            "archive",
            "mark_incompatible",
        }:
            raise ServiceError("PACKAGE_BAD_ACTION", 400)

        if action in {"upgrade", "install"} and cur_version and package_version:
            if semver_lt(package_version, cur_version):
                self._log_event(
                    actor,
                    track_id=track_id,
                    package_version=package_version,
                    action="downgrade_blocked",
                    detail={"from": cur_version, "to": package_version, **(detail or {})},
                )
                raise ServiceError("PACKAGE_UNSAFE_DOWNGRADE", 400)

        if action == "rollback":
            if cur_state == "revoked":
                raise ServiceError("PACKAGE_REVOKED", 403)
            to_state = cur_state if cur_state != "none" else "installed"
        elif action == "downgrade_blocked":
            to_state = cur_state if cur_state != "none" else "none"
        else:
            transition = PACKAGE_TRANSITIONS.get(action)
            if transition is None:
                raise ServiceError("PACKAGE_BAD_ACTION", 400)
            allowed_from, to_state = transition
            if cur_state not in allowed_from:
                raise ServiceError("PACKAGE_ILLEGAL_TRANSITION", 400)

        if action != "downgrade_blocked":
            version_to_store = package_version or cur_version
            self._set_state(track_id, to_state, version_to_store, detail)

        eid = self._log_event(
            actor,
            track_id=track_id,
            package_version=package_version,
            action=action,
            detail=detail,
        )
        st = self.get_state(track_id)
        return {
            "event_id": eid,
            "action": action,
            "track_id": track_id,
            "state": st["state"],
            "package_version": st["package_version"],
        }

    def _log_event(
        self,
        actor: Actor | None,
        *,
        track_id: str,
        package_version: str,
        action: str,
        detail: dict[str, Any] | None = None,
    ) -> str:
        # Map newer actions onto m006 CHECK-allowed labels for the event log.
        log_action = action
        if action in {"open", "activate"}:
            log_action = "upgrade"
        elif action in {"archive", "mark_incompatible"}:
            log_action = "deprecate"
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
                log_action,
                json.dumps({**(detail or {}), "requested_action": action}),
                actor.actor_id if actor else None,
                _now(),
            ),
        )
        self.conn.commit()
        return eid

    def assert_no_silent_downgrade(self, track_id: str, from_v: str, to_v: str) -> dict[str, Any]:
        if semver_lt(to_v, from_v):
            return self.record(
                None,
                track_id=track_id,
                package_version=to_v,
                action="downgrade_blocked",
                detail={"from": from_v, "to": to_v},
            )
        return self.record(
            None,
            track_id=track_id,
            package_version=to_v,
            action="upgrade",
            detail={"from": from_v},
        )

    def assert_can_open(self, track_id: str) -> dict[str, Any]:
        st = self.get_state(track_id)
        if st["state"] == "revoked":
            raise ServiceError("PACKAGE_REVOKED", 403)
        if st["state"] in {"none", "archived", "incompatible"}:
            raise ServiceError("PACKAGE_ILLEGAL_TRANSITION", 400)
        return self.record(
            None,
            track_id=track_id,
            package_version=st["package_version"],
            action="open",
        )

    def latest(self, track_id: str) -> dict[str, Any] | None:
        row = _row(
            self.conn,
            """
            SELECT * FROM package_lifecycle_events
            WHERE track_id=? ORDER BY created_at DESC LIMIT 1
            """,
            (track_id,),
        )
        return dict(row) if row else None
