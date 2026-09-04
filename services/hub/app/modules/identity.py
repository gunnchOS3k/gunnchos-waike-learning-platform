"""Identity, sites, sessions, and site-admin operations."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.auth import (
    Actor,
    Role,
    SYNTHETIC_ACTORS,
    hash_password,
    issue_session,
    revoke_session,
    verify_password,
)
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row, _rows


# Canonical multi-user E2E fixture passwords (synthetic only — never production secrets).
FIXTURE_PASSWORD = "WaikeTestPass1!"

PR3_USERS = [
    # site-alpha
    ("admin-alpha", "site-alpha", "admin-alpha", "Admin Alpha", [Role.SITE_ADMIN]),
    ("instructor-alpha", "site-alpha", "instructor-alpha", "Instructor Alpha", [Role.INSTRUCTOR]),
    ("grader-alpha", "site-alpha", "grader-alpha", "Grader Alpha", [Role.GRADER]),
    ("learner-alpha", "site-alpha", "learner-alpha", "Learner Alpha", [Role.LEARNER]),
    ("learner-beta", "site-alpha", "learner-beta", "Learner Beta", [Role.LEARNER]),
    # site-beta (isolation)
    ("admin-beta", "site-beta", "admin-beta", "Admin Beta", [Role.SITE_ADMIN]),
    ("instructor-beta", "site-beta", "instructor-beta", "Instructor Beta", [Role.INSTRUCTOR]),
    ("learner-gamma", "site-beta", "learner-gamma", "Learner Gamma", [Role.LEARNER]),
]


class IdentityService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def seed_sites_and_users(self) -> None:
        now = _now()
        for site_id, name in (("site-alpha", "Alpha Academy"), ("site-beta", "Beta Institute")):
            self.conn.execute(
                "INSERT OR IGNORE INTO sites(site_id, name, created_at) VALUES (?,?,?)",
                (site_id, name, now),
            )

        # Migrate PR2 synthetic actors into authoritative users (same IDs).
        for actor_id, meta in SYNTHETIC_ACTORS.items():
            self._upsert_user(
                user_id=actor_id,
                site_id=meta["site_id"],
                username=actor_id,
                display_name=meta["display_name"],
                roles=[Role(meta["role"])],
                password=FIXTURE_PASSWORD,
            )

        for user_id, site_id, username, display, roles in PR3_USERS:
            self._upsert_user(user_id, site_id, username, display, roles, FIXTURE_PASSWORD)

        # Keep actors table in sync for PR2 audit compatibility.
        for actor_id, meta in SYNTHETIC_ACTORS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
                (actor_id, meta["role"], meta["display_name"]),
            )
        for user_id, _site, _u, display, roles in PR3_USERS:
            self.conn.execute(
                "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
                (user_id, roles[0].value, display),
            )
        self.conn.commit()

    def _upsert_user(
        self,
        user_id: str,
        site_id: str,
        username: str,
        display_name: str,
        roles: list[Role],
        password: str,
    ) -> None:
        now = _now()
        existing = _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                VALUES (?,?,?,?,?,0,?)
                """,
                (user_id, site_id, username, display_name, hash_password(password), now),
            )
        for role in roles:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                VALUES (?,?,?,?,1,?)
                """,
                (_id("ra"), user_id, site_id, role.value, now),
            )

    def login(self, username: str, password: str, site_id: str | None = None) -> dict[str, Any]:
        if site_id:
            user = _row(
                self.conn,
                "SELECT * FROM users WHERE username=? AND site_id=?",
                (username, site_id),
            )
        else:
            user = _row(self.conn, "SELECT * FROM users WHERE username=?", (username,))
        if user is None:
            raise ServiceError("UNKNOWN_USER", 401)
        if int(user["disabled"]) == 1:
            raise ServiceError("USER_DISABLED", 403)
        if not verify_password(user["password_hash"], password):
            raise ServiceError("INVALID_PASSWORD", 401)
        session_id, token, expires = issue_session(self.conn, user["user_id"])
        roles = [
            r["role"]
            for r in _rows(
                self.conn,
                "SELECT role FROM role_assignments WHERE user_id=? AND site_id=? AND active=1",
                (user["user_id"], user["site_id"]),
            )
        ]
        _audit(self.conn, user["user_id"], "login", "session", session_id, {})
        self.conn.commit()
        return {
            "session_id": session_id,
            "token": token,
            "expires_at": expires,
            "user": {
                "user_id": user["user_id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "site_id": user["site_id"],
                "roles": roles,
            },
        }

    def logout(self, actor: Actor) -> dict[str, str]:
        if not actor.session_id:
            raise ServiceError("NO_SESSION", 400)
        revoke_session(self.conn, actor.session_id)
        _audit(self.conn, actor.actor_id, "logout", "session", actor.session_id, {})
        self.conn.commit()
        return {"status": "logged_out"}

    def me(self, actor: Actor) -> dict[str, Any]:
        return {
            "user_id": actor.actor_id,
            "username": actor.username,
            "display_name": actor.display_name,
            "site_id": actor.site_id,
            "roles": [r.value for r in actor.roles] or [actor.role.value],
            "session_id": actor.session_id,
        }

    # --- site admin -----------------------------------------------------------
    def create_user(
        self,
        actor: Actor,
        username: str,
        display_name: str,
        password: str,
        roles: list[str],
        site_id: str | None = None,
    ) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        target_site = site_id or actor.site_id
        if target_site != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        now = _now()
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        try:
            self.conn.execute(
                """
                INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                VALUES (?,?,?,?,?,0,?)
                """,
                (user_id, target_site, username, display_name, hash_password(password), now),
            )
        except sqlite3.IntegrityError as e:
            raise ServiceError("USERNAME_TAKEN", 409) from e
        for role in roles:
            if role not in {r.value for r in Role}:
                raise ServiceError("INVALID_ROLE", 400)
            self.conn.execute(
                """
                INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                VALUES (?,?,?,?,1,?)
                """,
                (_id("ra"), user_id, target_site, role, now),
            )
        self.conn.execute(
            "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
            (user_id, roles[0] if roles else Role.LEARNER.value, display_name),
        )
        _audit(self.conn, actor.actor_id, "create_user", "user", user_id, {"username": username})
        self.conn.commit()
        return self.get_user(actor, user_id)

    def disable_user(self, actor: Actor, user_id: str, disabled: bool = True) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        user = _row(self.conn, "SELECT * FROM users WHERE user_id=?", (user_id,))
        if not user:
            raise ServiceError("USER_NOT_FOUND", 404)
        if user["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        self.conn.execute("UPDATE users SET disabled=? WHERE user_id=?", (1 if disabled else 0, user_id))
        if disabled:
            self.conn.execute(
                "UPDATE sessions SET revoked=1, revoked_at=? WHERE user_id=? AND revoked=0",
                (_now(), user_id),
            )
        _audit(self.conn, actor.actor_id, "disable_user" if disabled else "enable_user", "user", user_id, {})
        self.conn.commit()
        return self.get_user(actor, user_id)

    def assign_role(self, actor: Actor, user_id: str, role: str) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        user = _row(self.conn, "SELECT * FROM users WHERE user_id=?", (user_id,))
        if not user:
            raise ServiceError("USER_NOT_FOUND", 404)
        if user["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        if role not in {r.value for r in Role}:
            raise ServiceError("INVALID_ROLE", 400)
        self.conn.execute(
            """
            INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
            VALUES (?,?,?,?,1,?)
            ON CONFLICT(user_id, site_id, role) DO UPDATE SET active=1
            """,
            (_id("ra"), user_id, actor.site_id, role, _now()),
        )
        _audit(self.conn, actor.actor_id, "assign_role", "user", user_id, {"role": role})
        self.conn.commit()
        return self.get_user(actor, user_id)

    def get_user(self, actor: Actor, user_id: str) -> dict[str, Any]:
        user = _row(
            self.conn,
            "SELECT user_id, site_id, username, display_name, disabled, created_at FROM users WHERE user_id=?",
            (user_id,),
        )
        if not user:
            raise ServiceError("USER_NOT_FOUND", 404)
        if user["site_id"] != actor.site_id and not actor.is_site_admin:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        if actor.is_site_admin and user["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        roles = [
            r["role"]
            for r in _rows(
                self.conn,
                "SELECT role FROM role_assignments WHERE user_id=? AND active=1",
                (user_id,),
            )
        ]
        return {**dict(user), "roles": roles}

    def list_users(self, actor: Actor) -> list[dict[str, Any]]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        rows = _rows(
            self.conn,
            "SELECT user_id, site_id, username, display_name, disabled, created_at FROM users WHERE site_id=? ORDER BY username",
            (actor.site_id,),
        )
        out = []
        for r in rows:
            d = dict(r)
            d["roles"] = [
                x["role"]
                for x in _rows(
                    self.conn,
                    "SELECT role FROM role_assignments WHERE user_id=? AND active=1",
                    (r["user_id"],),
                )
            ]
            out.append(d)
        return out
