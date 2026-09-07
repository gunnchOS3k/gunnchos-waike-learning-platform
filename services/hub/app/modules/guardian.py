"""Guardian least-privilege oversight (Gate D).

Guardians may view linked-learner progress summaries only.
They must never grade, access answer keys, administer sites, or mutate enrollment.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError, _id, _now, _row, _rows


class GuardianService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def seed_fixture_links(self) -> None:
        """Link guardian-alpha → learner-alpha on site-alpha (synthetic fixtures only)."""
        now = _now()
        link_id = "glink_alpha_ga_la"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO guardian_links(
              link_id, site_id, guardian_user_id, learner_user_id, active, created_at
            ) VALUES (?,?,?,?,1,?)
            """,
            (link_id, "site-alpha", "guardian-alpha", "learner-alpha", now),
        )
        self.conn.commit()

    def link(
        self,
        actor: Actor,
        *,
        guardian_user_id: str,
        learner_user_id: str,
    ) -> dict[str, Any]:
        if not actor.has_role(Role.SITE_ADMIN):
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        g = _row(
            self.conn,
            "SELECT user_id, site_id FROM users WHERE user_id=?",
            (guardian_user_id,),
        )
        learner = _row(
            self.conn,
            "SELECT user_id, site_id FROM users WHERE user_id=?",
            (learner_user_id,),
        )
        if g is None or learner is None:
            raise ServiceError("USER_NOT_FOUND", 404)
        if g["site_id"] != actor.site_id or learner["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        # Guardian must hold guardian role; learner must hold learner role.
        g_roles = {
            r["role"]
            for r in _rows(
                self.conn,
                "SELECT role FROM role_assignments WHERE user_id=? AND site_id=? AND active=1",
                (guardian_user_id, actor.site_id),
            )
        }
        l_roles = {
            r["role"]
            for r in _rows(
                self.conn,
                "SELECT role FROM role_assignments WHERE user_id=? AND site_id=? AND active=1",
                (learner_user_id, actor.site_id),
            )
        }
        if Role.GUARDIAN.value not in g_roles:
            raise ServiceError("GUARDIAN_ROLE_REQUIRED", 400)
        if Role.LEARNER.value not in l_roles:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 400)
        link_id = _id("glink")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO guardian_links(
              link_id, site_id, guardian_user_id, learner_user_id, active, created_at
            ) VALUES (?,?,?,?,1,?)
            ON CONFLICT(site_id, guardian_user_id, learner_user_id) DO UPDATE SET active=1
            """,
            (link_id, actor.site_id, guardian_user_id, learner_user_id, now),
        )
        self.conn.commit()
        return {
            "link_id": link_id,
            "guardian_user_id": guardian_user_id,
            "learner_user_id": learner_user_id,
            "site_id": actor.site_id,
        }

    def _assert_linked(self, actor: Actor, learner_user_id: str) -> None:
        if not actor.has_role(Role.GUARDIAN):
            raise ServiceError("GUARDIAN_ROLE_REQUIRED", 403)
        row = _row(
            self.conn,
            """
            SELECT link_id FROM guardian_links
            WHERE site_id=? AND guardian_user_id=? AND learner_user_id=? AND active=1
            """,
            (actor.site_id, actor.actor_id, learner_user_id),
        )
        if row is None:
            raise ServiceError("GUARDIAN_NOT_LINKED", 403)

    def list_linked_learners(self, actor: Actor) -> list[dict[str, Any]]:
        if not actor.has_role(Role.GUARDIAN):
            raise ServiceError("GUARDIAN_ROLE_REQUIRED", 403)
        rows = _rows(
            self.conn,
            """
            SELECT gl.learner_user_id, u.display_name, u.username
            FROM guardian_links gl
            JOIN users u ON u.user_id = gl.learner_user_id
            WHERE gl.site_id=? AND gl.guardian_user_id=? AND gl.active=1
            ORDER BY u.display_name
            """,
            (actor.site_id, actor.actor_id),
        )
        return [
            {
                "learner_user_id": r["learner_user_id"],
                "display_name": r["display_name"],
                "username": r["username"],
            }
            for r in rows
        ]

    def learner_overview(self, actor: Actor, learner_user_id: str) -> dict[str, Any]:
        """Progress summary only — no answer keys, rubric points detail, or instructor notes."""
        self._assert_linked(actor, learner_user_id)
        learner = _row(
            self.conn,
            "SELECT user_id, display_name, username, site_id FROM users WHERE user_id=?",
            (learner_user_id,),
        )
        if learner is None or learner["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)

        enrollments = _rows(
            self.conn,
            """
            SELECT e.section_id, s.code, s.title
            FROM enrollments e
            JOIN sections s ON s.section_id = e.section_id
            WHERE e.user_id=? AND s.site_id=? AND e.status='active'
            """,
            (learner_user_id, actor.site_id),
        )
        progress = _rows(
            self.conn,
            """
            SELECT section_id, lesson_id, percent_complete, updated_at
            FROM lesson_progress
            WHERE user_id=? AND site_id=?
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            (learner_user_id, actor.site_id),
        )
        # Mastery band only — never answer keys, rubric comments, or gap notes.
        mastery = _rows(
            self.conn,
            """
            SELECT assignment_id, score, threshold, mastered, evaluated_at
            FROM mastery_records
            WHERE learner_id=?
            ORDER BY evaluated_at DESC
            LIMIT 50
            """,
            (learner_user_id,),
        )
        overview = {
            "learner_user_id": learner_user_id,
            "display_name": learner["display_name"],
            "enrollments": [
                {"section_id": e["section_id"], "code": e["code"], "title": e["title"] if "title" in e.keys() else None}
                for e in enrollments
            ],
            "lesson_progress": [
                {
                    "section_id": p["section_id"],
                    "lesson_id": p["lesson_id"],
                    "percent_complete": p["percent_complete"],
                    "updated_at": p["updated_at"],
                }
                for p in progress
            ],
            "mastery_summary": [
                {
                    "assignment_id": m["assignment_id"],
                    "mastered": bool(m["mastered"]),
                    "score_vs_threshold": {
                        "score": m["score"],
                        "threshold": m["threshold"],
                    },
                    "evaluated_at": m["evaluated_at"],
                }
                for m in mastery
            ],
            "forbidden_fields_excluded": [
                "answer_key",
                "rubric_comments",
                "instructor_notes",
                "quiz_correct_responses",
                "gap_notes",
            ],
        }
        return overview
