"""Identity, sites, sessions, and site-admin operations."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from app.auth import (
    Actor,
    Role,
    SYNTHETIC_ACTORS,
    hash_password,
    issue_session,
    primary_role,
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

    def bootstrap_admin(
        self,
        *,
        site_id: str,
        site_name: str,
        username: str,
        display_name: str,
        password: str,
    ) -> dict[str, Any]:
        """One-time first-admin bootstrap: creates only the requested site + admin.

        Repeated calls never overwrite an existing admin password. Does not seed
        synthetic learners/instructors/sections.
        """
        site_id = (site_id or "").strip()
        site_name = (site_name or "").strip()
        username = (username or "").strip()
        display_name = (display_name or "").strip()
        if not site_id or not site_name:
            raise ServiceError("BOOTSTRAP_SITE_REQUIRED", 400)
        if not username or not display_name:
            raise ServiceError("BOOTSTRAP_ADMIN_REQUIRED", 400)
        if not password:
            raise ServiceError("BOOTSTRAP_PASSWORD_REQUIRED", 400)
        try:
            pwd_hash = hash_password(password)
        except ValueError as e:
            raise ServiceError("PASSWORD_TOO_SHORT", 400) from e

        existing_admin = _row(
            self.conn,
            """
            SELECT u.user_id, u.username FROM users u
            JOIN role_assignments r ON r.user_id = u.user_id AND r.site_id = u.site_id
            WHERE u.site_id=? AND r.role=? AND r.active=1
            LIMIT 1
            """,
            (site_id, Role.SITE_ADMIN.value),
        )
        if existing_admin is not None:
            return {
                "status": "already_bootstrapped",
                "site_id": site_id,
                "user_id": existing_admin["user_id"],
                "username": existing_admin["username"],
                "password_reset": False,
            }

        now = _now()
        user_id = f"admin_{uuid.uuid4().hex[:12]}"
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO sites(site_id, name, created_at) VALUES (?,?,?)",
                (site_id, site_name, now),
            )
            taken = _row(
                self.conn,
                "SELECT user_id FROM users WHERE site_id=? AND username=?",
                (site_id, username),
            )
            if taken is not None:
                raise ServiceError("USERNAME_TAKEN", 409)
            self.conn.execute(
                """
                INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                VALUES (?,?,?,?,?,0,?)
                """,
                (user_id, site_id, username, display_name, pwd_hash, now),
            )
            self.conn.execute(
                """
                INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                VALUES (?,?,?,?,1,?)
                """,
                (_id("ra"), user_id, site_id, Role.SITE_ADMIN.value, now),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
                (user_id, Role.SITE_ADMIN.value, display_name),
            )
            _audit(
                self.conn,
                user_id,
                "bootstrap_admin",
                "user",
                user_id,
                {"site_id": site_id, "username": username},
            )
            self.conn.commit()
        except ServiceError:
            self.conn.rollback()
            raise
        except Exception:
            self.conn.rollback()
            raise
        return {
            "status": "created",
            "site_id": site_id,
            "user_id": user_id,
            "username": username,
            "password_reset": False,
        }

    def login(self, username: str, password: str, site_id: str | None = None) -> dict[str, Any]:
        if not site_id or not str(site_id).strip():
            raise ServiceError("SITE_ID_REQUIRED", 400)
        site_id = str(site_id).strip()
        # Site-scoped lookup only — wrong site looks like unknown user (no cross-site leak).
        user = _row(
            self.conn,
            "SELECT * FROM users WHERE username=? AND site_id=?",
            (username, site_id),
        )
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

        # Validate-before-mutate: nothing is written until all inputs are accepted.
        username = (username or "").strip()
        display_name = (display_name or "").strip()
        if not username:
            raise ServiceError("INVALID_USERNAME", 400)
        if not display_name:
            raise ServiceError("INVALID_DISPLAY_NAME", 400)
        if not roles:
            raise ServiceError("ROLES_REQUIRED", 400)
        valid_roles = {r.value for r in Role}
        for role in roles:
            if role not in valid_roles:
                raise ServiceError("INVALID_ROLE", 400)
        try:
            pwd_hash = hash_password(password)
        except ValueError as e:
            raise ServiceError("PASSWORD_TOO_SHORT", 400) from e

        dup = _row(
            self.conn,
            "SELECT user_id FROM users WHERE site_id=? AND username=?",
            (target_site, username),
        )
        if dup is not None:
            raise ServiceError("USERNAME_TAKEN", 409)

        now = _now()
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        primary = primary_role([Role(r) for r in roles]).value
        try:
            self.conn.execute(
                """
                INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
                VALUES (?,?,?,?,?,0,?)
                """,
                (user_id, target_site, username, display_name, pwd_hash, now),
            )
            for role in roles:
                self.conn.execute(
                    """
                    INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
                    VALUES (?,?,?,?,1,?)
                    """,
                    (_id("ra"), user_id, target_site, role, now),
                )
            self.conn.execute(
                "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
                (user_id, primary, display_name),
            )
            _audit(self.conn, actor.actor_id, "create_user", "user", user_id, {"username": username})
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            self.conn.rollback()
            raise ServiceError("USERNAME_TAKEN", 409) from e
        except Exception:
            self.conn.rollback()
            raise
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

    def deactivate_role(self, actor: Actor, user_id: str, role: str) -> dict[str, Any]:
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
            UPDATE role_assignments SET active=0
            WHERE user_id=? AND site_id=? AND role=?
            """,
            (user_id, actor.site_id, role),
        )
        _audit(self.conn, actor.actor_id, "deactivate_role", "user", user_id, {"role": role})
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
