from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import Header, HTTPException


class Role(str, Enum):
    LEARNER = "learner"
    INSTRUCTOR = "instructor"
    GRADER = "grader"
    SITE_ADMIN = "site_admin"


# Synthetic fixtures only — PR3 owns full multi-user identity.
SYNTHETIC_ACTORS: dict[str, dict[str, str]] = {
    "learner-a": {"role": Role.LEARNER.value, "display_name": "Learner A"},
    "learner-b": {"role": Role.LEARNER.value, "display_name": "Learner B"},
    "instructor-1": {"role": Role.INSTRUCTOR.value, "display_name": "Instructor One"},
    "grader-1": {"role": Role.GRADER.value, "display_name": "Grader One"},
}


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Role
    display_name: str

    @property
    def is_instructor_side(self) -> bool:
        return self.role in {Role.INSTRUCTOR, Role.GRADER, Role.SITE_ADMIN}

    @property
    def is_learner(self) -> bool:
        return self.role == Role.LEARNER


def require_actor(
    x_waike_actor_id: str | None = Header(default=None, alias="X-Waike-Actor-Id"),
    x_waike_actor_role: str | None = Header(default=None, alias="X-Waike-Actor-Role"),
) -> Actor:
    if not x_waike_actor_id or not x_waike_actor_role:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    fixture = SYNTHETIC_ACTORS.get(x_waike_actor_id)
    if fixture is None:
        raise HTTPException(status_code=401, detail="UNKNOWN_ACTOR")
    if fixture["role"] != x_waike_actor_role:
        raise HTTPException(status_code=403, detail="ROLE_MISMATCH")
    return Actor(
        actor_id=x_waike_actor_id,
        role=Role(fixture["role"]),
        display_name=fixture["display_name"],
    )


def require_learner(actor: Actor) -> Actor:
    if not actor.is_learner:
        raise HTTPException(status_code=403, detail="LEARNER_ROLE_REQUIRED")
    return actor


def require_instructor_side(actor: Actor) -> Actor:
    if not actor.is_instructor_side:
        raise HTTPException(status_code=403, detail="INSTRUCTOR_ROLE_REQUIRED")
    return actor
