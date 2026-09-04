"""PR3 identity auth: production sessions by default; fixture headers only when explicitly enabled."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.auth.passwords import hash_password, verify_password

__all__ = [
    "Role",
    "Actor",
    "SYNTHETIC_ACTORS",
    "hash_password",
    "verify_password",
    "require_actor",
    "require_learner",
    "require_instructor_side",
    "require_site_admin",
    "session_token_hash",
    "issue_session",
    "revoke_session",
]


class Role(str, Enum):
    LEARNER = "learner"
    INSTRUCTOR = "instructor"
    GRADER = "grader"
    SITE_ADMIN = "site_admin"


# Legacy fixture actor IDs preserved for PR2 regression when fixture_auth_enabled=True.
SYNTHETIC_ACTORS: dict[str, dict[str, str]] = {
    "learner-a": {"role": Role.LEARNER.value, "display_name": "Learner A", "site_id": "site-alpha"},
    "learner-b": {"role": Role.LEARNER.value, "display_name": "Learner B", "site_id": "site-alpha"},
    "instructor-1": {"role": Role.INSTRUCTOR.value, "display_name": "Instructor One", "site_id": "site-alpha"},
    "grader-1": {"role": Role.GRADER.value, "display_name": "Grader One", "site_id": "site-alpha"},
}


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Role
    display_name: str
    site_id: str
    roles: tuple[Role, ...] = ()
    session_id: str | None = None
    username: str = ""

    @property
    def is_instructor_side(self) -> bool:
        return self.role in {Role.INSTRUCTOR, Role.GRADER, Role.SITE_ADMIN} or any(
            r in {Role.INSTRUCTOR, Role.GRADER, Role.SITE_ADMIN} for r in self.roles
        )

    @property
    def is_learner(self) -> bool:
        return self.role == Role.LEARNER or Role.LEARNER in self.roles

    @property
    def is_site_admin(self) -> bool:
        return self.role == Role.SITE_ADMIN or Role.SITE_ADMIN in self.roles


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_expiry(raw: str) -> datetime:
    # SQLite stores ISO-ish UTC
    if raw.endswith("Z"):
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)


def issue_session(conn: sqlite3.Connection, user_id: str, ttl_hours: int = 12) -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    session_id = f"sess_{secrets.token_hex(8)}"
    now = _now()
    expires = now + timedelta(hours=ttl_hours)
    expires_s = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    created_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO sessions(session_id, user_id, token_hash, expires_at, revoked, created_at)
        VALUES (?,?,?,?,0,?)
        """,
        (session_id, user_id, session_token_hash(token), expires_s, created_s),
    )
    conn.commit()
    return session_id, token, expires_s


def revoke_session(conn: sqlite3.Connection, session_id: str) -> None:
    now = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE sessions SET revoked=1, revoked_at=? WHERE session_id=?",
        (now, session_id),
    )
    conn.commit()


def _roles_for(conn: sqlite3.Connection, user_id: str, site_id: str) -> list[Role]:
    rows = conn.execute(
        "SELECT role FROM role_assignments WHERE user_id=? AND site_id=? AND active=1",
        (user_id, site_id),
    ).fetchall()
    return [Role(r[0] if not hasattr(r, "keys") else r["role"]) for r in rows]


def _actor_from_user(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    preferred_role: Role | None = None,
    session_id: str | None = None,
) -> Actor:
    roles = _roles_for(conn, user_row["user_id"], user_row["site_id"])
    if not roles:
        raise HTTPException(status_code=403, detail="NO_ACTIVE_ROLE")
    role = preferred_role if preferred_role in roles else roles[0]
    return Actor(
        actor_id=user_row["user_id"],
        role=role,
        display_name=user_row["display_name"],
        site_id=user_row["site_id"],
        roles=tuple(roles),
        session_id=session_id,
        username=user_row["username"],
    )


def _resolve_production(request: Request, authorization: str | None) -> Actor:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    token = authorization.split(" ", 1)[1].strip()
    if not token or len(token) < 16:
        raise HTTPException(status_code=401, detail="MALFORMED_TOKEN")
    conn: sqlite3.Connection = request.app.state.db
    th = session_token_hash(token)
    row = conn.execute(
        """
        SELECT s.session_id, s.expires_at, s.revoked, u.user_id, u.site_id, u.display_name,
               u.username, u.disabled
        FROM sessions s
        JOIN users u ON u.user_id = s.user_id
        WHERE s.token_hash=?
        """,
        (th,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="INVALID_SESSION")
    if int(row["revoked"]) == 1:
        raise HTTPException(status_code=401, detail="SESSION_REVOKED")
    if int(row["disabled"]) == 1:
        raise HTTPException(status_code=403, detail="USER_DISABLED")
    if _parse_expiry(row["expires_at"]) <= _now():
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED")
    return _actor_from_user(conn, row, session_id=row["session_id"])


def _resolve_fixture(
    request: Request,
    actor_id: str | None,
    actor_role: str | None,
) -> Actor:
    if not actor_id or not actor_role:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    try:
        claimed = Role(actor_role)
    except ValueError as e:
        raise HTTPException(status_code=403, detail="ROLE_MISMATCH") from e

    conn: sqlite3.Connection = request.app.state.db
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (actor_id,)).fetchone()
    if user is not None:
        if int(user["disabled"]) == 1:
            raise HTTPException(status_code=403, detail="USER_DISABLED")
        roles = _roles_for(conn, actor_id, user["site_id"])
        if claimed not in roles:
            raise HTTPException(status_code=403, detail="ROLE_MISMATCH")
        return _actor_from_user(conn, user, preferred_role=claimed)

    fixture = SYNTHETIC_ACTORS.get(actor_id)
    if fixture is None:
        raise HTTPException(status_code=401, detail="UNKNOWN_ACTOR")
    if fixture["role"] != actor_role:
        raise HTTPException(status_code=403, detail="ROLE_MISMATCH")
    return Actor(
        actor_id=actor_id,
        role=Role(fixture["role"]),
        display_name=fixture["display_name"],
        site_id=fixture["site_id"],
        roles=(Role(fixture["role"]),),
        username=actor_id,
    )


async def require_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_waike_actor_id: Annotated[str | None, Header(alias="X-Waike-Actor-Id")] = None,
    x_waike_actor_role: Annotated[str | None, Header(alias="X-Waike-Actor-Role")] = None,
) -> Actor:
    cfg = request.app.state.config
    production = bool(cfg.production_auth_enabled)
    fixture = bool(cfg.fixture_auth_enabled)

    # Reject client-trusted fixture headers in production mode.
    if production and not fixture and (x_waike_actor_id or x_waike_actor_role):
        raise HTTPException(status_code=401, detail="FIXTURE_AUTH_REJECTED")

    if production and not fixture:
        return _resolve_production(request, authorization)

    if fixture:
        # Prefer session when both present (tests may use either).
        if authorization and authorization.lower().startswith("bearer "):
            return _resolve_production(request, authorization)
        return _resolve_fixture(request, x_waike_actor_id, x_waike_actor_role)

    # Neither mode enabled — refuse.
    raise HTTPException(status_code=401, detail="AUTH_DISABLED")


def require_learner(actor: Actor) -> Actor:
    if actor.role != Role.LEARNER:
        raise HTTPException(status_code=403, detail="LEARNER_ROLE_REQUIRED")
    return actor


def require_instructor_side(actor: Actor) -> Actor:
    if actor.role not in {Role.INSTRUCTOR, Role.GRADER, Role.SITE_ADMIN}:
        raise HTTPException(status_code=403, detail="INSTRUCTOR_ROLE_REQUIRED")
    return actor


def require_site_admin(actor: Actor) -> Actor:
    if actor.role != Role.SITE_ADMIN:
        raise HTTPException(status_code=403, detail="SITE_ADMIN_REQUIRED")
    return actor
