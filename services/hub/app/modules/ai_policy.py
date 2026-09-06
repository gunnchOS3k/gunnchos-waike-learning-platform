"""Server-authoritative AI policy for Gate B (gunnchAI integration).

Policies: AI_ALLOWED | AI_HINTS_ONLY | AI_DISABLED | AI_INSTRUCTOR_DEFINED.
Learners cannot alter policy. Effective policy resolves activity > assessment > section.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row

AI_POLICIES = frozenset(
    {"AI_ALLOWED", "AI_HINTS_ONLY", "AI_DISABLED", "AI_INSTRUCTOR_DEFINED"}
)

LEARNER_CAPABILITIES = frozenset(
    {
        "explain",
        "hint",
        "misconception",
        "remediation",
        "citation",
        "navigate",
        "lab_troubleshoot",
        "reflect",
    }
)

HINTS_ONLY_CAPABILITIES = frozenset({"hint", "navigate", "reflect"})

INSTRUCTOR_CAPABILITIES = frozenset(
    {
        "feedback_suggest",
        "rubric_refine",
        "misconception_cluster",
        "remediation_suggest",
        "lesson_adapt",
        "grading_triage",
    }
)


class AiPolicyService:
    def __init__(self, conn: sqlite3.Connection, sections: Any) -> None:
        self.conn = conn
        self.sections = sections

    def set_policy(
        self,
        actor: Actor,
        *,
        section_id: str,
        policy: str,
        scope: str = "section",
        assessment_id: str | None = None,
        activity_id: str | None = None,
        instructor_defined: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if actor.is_learner and not actor.is_instructor_side:
            raise ServiceError("AI_POLICY_LEARNER_CANNOT_SET", 403)
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        if policy not in AI_POLICIES:
            raise ServiceError("AI_POLICY_INVALID", 400)
        if scope not in {"section", "assessment", "activity"}:
            raise ServiceError("AI_POLICY_SCOPE_INVALID", 400)
        self.sections.require_staff_scope(actor, section_id)
        if scope == "section":
            assessment_id = None
            activity_id = None
        elif scope == "assessment":
            if not assessment_id:
                raise ServiceError("ASSESSMENT_ID_REQUIRED", 400)
            activity_id = None
        elif scope == "activity":
            if not activity_id:
                raise ServiceError("ACTIVITY_ID_REQUIRED", 400)

        defined = instructor_defined or {}
        if policy == "AI_INSTRUCTOR_DEFINED":
            caps = defined.get("allowed_capabilities")
            if not isinstance(caps, list) or not caps:
                raise ServiceError("AI_INSTRUCTOR_DEFINED_CAPS_REQUIRED", 400)
            bad = [c for c in caps if c not in LEARNER_CAPABILITIES and c not in INSTRUCTOR_CAPABILITIES]
            if bad:
                raise ServiceError("AI_CAPABILITY_UNKNOWN", 400)

        now = _now()
        existing = self._find_row(section_id, scope, assessment_id, activity_id)
        if existing:
            self.conn.execute(
                """
                UPDATE ai_policies
                SET policy=?, instructor_defined_json=?, set_by=?, updated_at=?
                WHERE policy_id=?
                """,
                (policy, json.dumps(defined), actor.actor_id, now, existing["policy_id"]),
            )
            policy_id = existing["policy_id"]
        else:
            policy_id = _id("aipol")
            self.conn.execute(
                """
                INSERT INTO ai_policies(
                  policy_id, site_id, scope, section_id, assessment_id, activity_id,
                  policy, instructor_defined_json, set_by, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    policy_id,
                    actor.site_id,
                    scope,
                    section_id,
                    assessment_id,
                    activity_id,
                    policy,
                    json.dumps(defined),
                    actor.actor_id,
                    now,
                    now,
                ),
            )
        _audit(
            self.conn,
            actor.actor_id,
            "ai_policy.set",
            "ai_policy",
            policy_id,
            {
                "section_id": section_id,
                "scope": scope,
                "policy": policy,
                "assessment_id": assessment_id,
                "activity_id": activity_id,
            },
        )
        self.conn.commit()
        return self.get_policy_record(policy_id)

    def get_policy_record(self, policy_id: str) -> dict[str, Any]:
        row = _row(self.conn, "SELECT * FROM ai_policies WHERE policy_id=?", (policy_id,))
        if not row:
            raise ServiceError("AI_POLICY_NOT_FOUND", 404)
        return self._public(row)

    def resolve_effective(
        self,
        section_id: str,
        *,
        assessment_id: str | None = None,
        activity_id: str | None = None,
    ) -> dict[str, Any]:
        """Most-specific wins: activity > assessment > section > default AI_ALLOWED."""
        if activity_id:
            row = _row(
                self.conn,
                """
                SELECT * FROM ai_policies
                WHERE section_id=? AND scope='activity' AND activity_id=?
                """,
                (section_id, activity_id),
            )
            if row:
                return self._effective_from_row(row, "activity")
        if assessment_id:
            row = _row(
                self.conn,
                """
                SELECT * FROM ai_policies
                WHERE section_id=? AND scope='assessment' AND assessment_id=?
                """,
                (section_id, assessment_id),
            )
            if row:
                return self._effective_from_row(row, "assessment")
        row = _row(
            self.conn,
            "SELECT * FROM ai_policies WHERE section_id=? AND scope='section'",
            (section_id,),
        )
        if row:
            return self._effective_from_row(row, "section")
        return {
            "policy": "AI_ALLOWED",
            "scope": "default",
            "section_id": section_id,
            "assessment_id": assessment_id,
            "activity_id": activity_id,
            "instructor_defined": {},
            "allowed_learner_capabilities": sorted(LEARNER_CAPABILITIES),
            "allowed_instructor_capabilities": sorted(INSTRUCTOR_CAPABILITIES),
            "source": "default",
        }

    def assert_capability_allowed(
        self,
        effective: dict[str, Any],
        capability: str,
        *,
        learner_facing: bool,
    ) -> None:
        policy = effective["policy"]
        if policy == "AI_DISABLED":
            raise ServiceError("AI_DISABLED", 403)
        if learner_facing:
            allowed = set(effective.get("allowed_learner_capabilities") or [])
            if capability not in LEARNER_CAPABILITIES:
                raise ServiceError("AI_CAPABILITY_UNKNOWN", 400)
            if capability not in allowed:
                raise ServiceError("AI_CAPABILITY_FORBIDDEN", 403)
        else:
            allowed = set(effective.get("allowed_instructor_capabilities") or [])
            if capability not in INSTRUCTOR_CAPABILITIES:
                raise ServiceError("AI_CAPABILITY_UNKNOWN", 400)
            # Instructor suggestions remain available unless section AI is fully disabled.
            if policy == "AI_DISABLED":
                raise ServiceError("AI_DISABLED", 403)
            if policy == "AI_INSTRUCTOR_DEFINED" and capability not in allowed:
                raise ServiceError("AI_CAPABILITY_FORBIDDEN", 403)

    def _find_row(
        self,
        section_id: str,
        scope: str,
        assessment_id: str | None,
        activity_id: str | None,
    ) -> sqlite3.Row | None:
        if scope == "section":
            return _row(
                self.conn,
                "SELECT * FROM ai_policies WHERE section_id=? AND scope='section'",
                (section_id,),
            )
        if scope == "assessment":
            return _row(
                self.conn,
                """
                SELECT * FROM ai_policies
                WHERE section_id=? AND scope='assessment' AND assessment_id=?
                """,
                (section_id, assessment_id),
            )
        return _row(
            self.conn,
            """
            SELECT * FROM ai_policies
            WHERE section_id=? AND scope='activity' AND activity_id=?
            """,
            (section_id, activity_id),
        )

    def _effective_from_row(self, row: sqlite3.Row, matched_scope: str) -> dict[str, Any]:
        defined = json.loads(row["instructor_defined_json"] or "{}")
        policy = row["policy"]
        learner_caps, instructor_caps = self._caps_for(policy, defined)
        return {
            "policy": policy,
            "scope": matched_scope,
            "section_id": row["section_id"],
            "assessment_id": row["assessment_id"],
            "activity_id": row["activity_id"],
            "instructor_defined": defined,
            "allowed_learner_capabilities": sorted(learner_caps),
            "allowed_instructor_capabilities": sorted(instructor_caps),
            "source": row["policy_id"],
            "set_by": row["set_by"],
            "updated_at": row["updated_at"],
        }

    def _caps_for(
        self, policy: str, defined: dict[str, Any]
    ) -> tuple[set[str], set[str]]:
        if policy == "AI_DISABLED":
            return set(), set()
        if policy == "AI_HINTS_ONLY":
            return set(HINTS_ONLY_CAPABILITIES), set(INSTRUCTOR_CAPABILITIES)
        if policy == "AI_INSTRUCTOR_DEFINED":
            raw = defined.get("allowed_capabilities") or []
            learner = {c for c in raw if c in LEARNER_CAPABILITIES}
            instructor = {c for c in raw if c in INSTRUCTOR_CAPABILITIES}
            # Instructor suggestions default on unless explicitly emptied for instructor set.
            if not instructor and any(c in INSTRUCTOR_CAPABILITIES for c in raw):
                instructor = set()
            elif not any(c in INSTRUCTOR_CAPABILITIES for c in raw):
                instructor = set(INSTRUCTOR_CAPABILITIES)
            return learner, instructor
        return set(LEARNER_CAPABILITIES), set(INSTRUCTOR_CAPABILITIES)

    def _public(self, row: sqlite3.Row) -> dict[str, Any]:
        defined = json.loads(row["instructor_defined_json"] or "{}")
        learner_caps, instructor_caps = self._caps_for(row["policy"], defined)
        return {
            "policy_id": row["policy_id"],
            "site_id": row["site_id"],
            "scope": row["scope"],
            "section_id": row["section_id"],
            "assessment_id": row["assessment_id"],
            "activity_id": row["activity_id"],
            "policy": row["policy"],
            "instructor_defined": defined,
            "allowed_learner_capabilities": sorted(learner_caps),
            "allowed_instructor_capabilities": sorted(instructor_caps),
            "set_by": row["set_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
