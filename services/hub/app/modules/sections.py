"""Sections, enrollment, and site-scoped authorization helpers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row, _rows


class SectionService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def seed_digital_confidence_section(self, source_commit: str = "") -> dict[str, Any]:
        now = _now()
        package_id = "pkg_digital_confidence_w01"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO packages(package_id, module_id, title, source_commit, immutable, created_at)
            VALUES (?,?,?,?,1,?)
            """,
            (package_id, "DIGITAL_CONFIDENCE", "Digital Confidence W01", source_commit, now),
        )
        section_id = "sec_alpha_dc_w01"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sections(section_id, site_id, package_id, code, title, published, created_at)
            VALUES (?,?,?,?,?,1,?)
            """,
            (section_id, "site-alpha", package_id, "DC-W01-A", "Digital Confidence — Alpha", now),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at)
            VALUES (?,?,?,?)
            """,
            (section_id, "{}", "Published for PR3 multi-user E2E", now),
        )
        for uid in ("instructor-alpha", "instructor-1"):
            if _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", (uid,)):
                self.conn.execute(
                    "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
                    (section_id, uid, now),
                )
        for uid in ("grader-alpha", "grader-1"):
            if _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", (uid,)):
                self.conn.execute(
                    "INSERT OR IGNORE INTO section_graders(section_id, user_id, assigned_at) VALUES (?,?,?)",
                    (section_id, uid, now),
                )
        for uid in ("learner-alpha", "learner-beta", "learner-a", "learner-b"):
            if _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", (uid,)):
                self._enroll_unchecked(section_id, uid, now)
        sec_beta = "sec_beta_dc_w01"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sections(section_id, site_id, package_id, code, title, published, created_at)
            VALUES (?,?,?,?,?,1,?)
            """,
            (sec_beta, "site-beta", package_id, "DC-W01-B", "Digital Confidence — Beta", now),
        )
        if _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", ("instructor-beta",)):
            self.conn.execute(
                "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
                (sec_beta, "instructor-beta", now),
            )
        if _row(self.conn, "SELECT user_id FROM users WHERE user_id=?", ("learner-gamma",)):
            self._enroll_unchecked(sec_beta, "learner-gamma", now)
        self.conn.commit()
        return self.get_section_public(section_id)

    def _enroll_unchecked(self, section_id: str, user_id: str, now: str) -> None:
        active = _row(
            self.conn,
            "SELECT enrollment_id FROM enrollments WHERE section_id=? AND user_id=? AND status='active'",
            (section_id, user_id),
        )
        if active:
            return
        self.conn.execute(
            """
            INSERT INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
            VALUES (?,?,?,'active',?)
            """,
            (_id("enr"), section_id, user_id, now),
        )

    def create_section(
        self,
        actor: Actor,
        code: str,
        title: str,
        package_id: str,
        published: bool = False,
    ) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        pkg = _row(self.conn, "SELECT * FROM packages WHERE package_id=?", (package_id,))
        if not pkg:
            raise ServiceError("PACKAGE_NOT_FOUND", 404)
        now = _now()
        section_id = _id("sec")
        try:
            self.conn.execute(
                """
                INSERT INTO sections(section_id, site_id, package_id, code, title, published, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (section_id, actor.site_id, package_id, code, title, 1 if published else 0, now),
            )
        except sqlite3.IntegrityError as e:
            raise ServiceError("SECTION_CODE_TAKEN", 409) from e
        self.conn.execute(
            """
            INSERT INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at)
            VALUES (?,?,?,?)
            """,
            (section_id, "{}", "", now),
        )
        _audit(self.conn, actor.actor_id, "create_section", "section", section_id, {"code": code})
        self.conn.commit()
        return self.get_section(actor, section_id)

    def assign_instructor(self, actor: Actor, section_id: str, user_id: str) -> dict[str, Any]:
        self._require_admin_same_site(actor, section_id)
        self._require_user_same_site(actor, user_id)
        self.conn.execute(
            "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, user_id, _now()),
        )
        _audit(self.conn, actor.actor_id, "assign_instructor", "section", section_id, {"user_id": user_id})
        self.conn.commit()
        return self.get_section(actor, section_id)

    def assign_grader(self, actor: Actor, section_id: str, user_id: str) -> dict[str, Any]:
        self._require_admin_same_site(actor, section_id)
        self._require_user_same_site(actor, user_id)
        self.conn.execute(
            "INSERT OR IGNORE INTO section_graders(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, user_id, _now()),
        )
        _audit(self.conn, actor.actor_id, "assign_grader", "section", section_id, {"user_id": user_id})
        self.conn.commit()
        return self.get_section(actor, section_id)

    def enroll(self, actor: Actor, section_id: str, user_id: str) -> dict[str, Any]:
        self._require_admin_same_site(actor, section_id)
        self._require_user_same_site(actor, user_id)
        active = _row(
            self.conn,
            "SELECT enrollment_id FROM enrollments WHERE section_id=? AND user_id=? AND status='active'",
            (section_id, user_id),
        )
        if active:
            raise ServiceError("DUPLICATE_ACTIVE_ENROLLMENT", 409)
        eid = _id("enr")
        self.conn.execute(
            """
            INSERT INTO enrollments(enrollment_id, section_id, user_id, status, enrolled_at)
            VALUES (?,?,?,'active',?)
            """,
            (eid, section_id, user_id, _now()),
        )
        _audit(self.conn, actor.actor_id, "enroll", "enrollment", eid, {"user_id": user_id})
        self.conn.commit()
        return dict(_row(self.conn, "SELECT * FROM enrollments WHERE enrollment_id=?", (eid,)))

    def deactivate_enrollment(self, actor: Actor, enrollment_id: str) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        enr = _row(self.conn, "SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,))
        if not enr:
            raise ServiceError("ENROLLMENT_NOT_FOUND", 404)
        sec = _row(self.conn, "SELECT * FROM sections WHERE section_id=?", (enr["section_id"],))
        if not sec or sec["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        now = _now()
        self.conn.execute(
            "UPDATE enrollments SET status='inactive', deactivated_at=? WHERE enrollment_id=?",
            (now, enrollment_id),
        )
        _audit(self.conn, actor.actor_id, "deactivate_enrollment", "enrollment", enrollment_id, {})
        self.conn.commit()
        return dict(_row(self.conn, "SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)))

    def update_runtime_metadata(
        self,
        actor: Actor,
        section_id: str,
        due_override: dict | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if not self.can_instruct(actor, section_id) and not actor.is_site_admin:
            raise ServiceError("FORBIDDEN", 403)
        sec = self._section_same_site(actor, section_id)
        meta = _row(self.conn, "SELECT * FROM section_runtime_metadata WHERE section_id=?", (section_id,))
        due = json.dumps(due_override) if due_override is not None else (meta["due_override_json"] if meta else "{}")
        pub = notes if notes is not None else (meta["publish_notes"] if meta else "")
        self.conn.execute(
            """
            INSERT INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(section_id) DO UPDATE SET
              due_override_json=excluded.due_override_json,
              publish_notes=excluded.publish_notes,
              updated_at=excluded.updated_at
            """,
            (section_id, due, pub, _now()),
        )
        self.conn.commit()
        return self.get_section(actor, sec["section_id"])

    def list_sections_for_actor(self, actor: Actor) -> list[dict[str, Any]]:
        if actor.is_learner and not actor.is_instructor_side and not actor.is_site_admin:
            rows = _rows(
                self.conn,
                """
                SELECT s.* FROM sections s
                JOIN enrollments e ON e.section_id = s.section_id
                WHERE e.user_id=? AND e.status='active' AND s.site_id=?
                ORDER BY s.code
                """,
                (actor.actor_id, actor.site_id),
            )
        elif actor.is_site_admin:
            rows = _rows(
                self.conn,
                "SELECT * FROM sections WHERE site_id=? ORDER BY code",
                (actor.site_id,),
            )
        else:
            rows = _rows(
                self.conn,
                """
                SELECT DISTINCT s.* FROM sections s
                LEFT JOIN section_instructors si ON si.section_id = s.section_id AND si.user_id=?
                LEFT JOIN section_graders sg ON sg.section_id = s.section_id AND sg.user_id=?
                WHERE s.site_id=? AND (si.user_id IS NOT NULL OR sg.user_id IS NOT NULL)
                ORDER BY s.code
                """,
                (actor.actor_id, actor.actor_id, actor.site_id),
            )
        return [self._enrich(dict(r)) for r in rows]

    def get_section(self, actor: Actor, section_id: str) -> dict[str, Any]:
        sec = self._section_same_site(actor, section_id)
        if actor.is_site_admin:
            return self._enrich(dict(sec))
        if self.can_instruct(actor, section_id) or self.can_grade(actor, section_id):
            return self._enrich(dict(sec))
        if actor.is_learner and self.is_enrolled(actor.actor_id, section_id):
            return self._enrich(dict(sec))
        if actor.is_learner:
            raise ServiceError("NOT_ENROLLED", 403)
        raise ServiceError("FORBIDDEN", 403)

    def get_section_public(self, section_id: str) -> dict[str, Any]:
        sec = _row(self.conn, "SELECT * FROM sections WHERE section_id=?", (section_id,))
        if not sec:
            raise ServiceError("SECTION_NOT_FOUND", 404)
        return self._enrich(dict(sec))

    def roster(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        if not (self.can_instruct(actor, section_id) or actor.is_site_admin):
            raise ServiceError("FORBIDDEN", 403)
        self._section_same_site(actor, section_id)
        rows = _rows(
            self.conn,
            """
            SELECT e.enrollment_id, e.user_id, e.status, e.enrolled_at, u.display_name, u.username
            FROM enrollments e
            JOIN users u ON u.user_id = e.user_id
            WHERE e.section_id=?
            ORDER BY u.username
            """,
            (section_id,),
        )
        return [dict(r) for r in rows]

    def learner_home(self, actor: Actor) -> list[dict[str, Any]]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        # Enrollment-scoped even for multi-role actors (primary may be instructor/admin).
        enrolled = _rows(
            self.conn,
            """
            SELECT s.* FROM sections s
            JOIN enrollments e ON e.section_id = s.section_id
            WHERE e.user_id=? AND e.status='active' AND s.site_id=?
            ORDER BY s.code
            """,
            (actor.actor_id, actor.site_id),
        )
        sections = [self._enrich(dict(r)) for r in enrolled]
        out = []
        for s in sections:
            mastery = _row(
                self.conn,
                """
                SELECT m.mastered, m.score, m.gap_notes, m.assignment_id
                FROM mastery_records m
                JOIN submissions sub ON sub.submission_id = m.submission_id
                WHERE m.learner_id=? AND (sub.section_id=? OR sub.section_id IS NULL)
                ORDER BY m.evaluated_at DESC LIMIT 1
                """,
                (actor.actor_id, s["section_id"]),
            )
            feedback = _rows(
                self.conn,
                """
                SELECT f.feedback_id, f.body, f.created_at, s.assignment_id
                FROM feedback f
                JOIN submissions s ON s.submission_id = f.submission_id
                WHERE s.learner_id=? AND f.visible_to_learner=1
                  AND (s.section_id=? OR s.section_id IS NULL)
                ORDER BY f.created_at DESC LIMIT 5
                """,
                (actor.actor_id, s["section_id"]),
            )
            out.append(
                {
                    **s,
                    "mastery": dict(mastery) if mastery else None,
                    "recent_feedback": [dict(f) for f in feedback],
                }
            )
        return out

    def instructor_dashboard(self, actor: Actor, section_id: str) -> dict[str, Any]:
        if not (self.can_instruct(actor, section_id) or self.can_grade(actor, section_id) or actor.is_site_admin):
            raise ServiceError("FORBIDDEN", 403)
        sec = self.get_section(actor, section_id)
        enrolled = _row(
            self.conn,
            "SELECT COUNT(*) AS c FROM enrollments WHERE section_id=? AND status='active'",
            (section_id,),
        )["c"]
        submitted = _row(
            self.conn,
            "SELECT COUNT(*) AS c FROM submissions WHERE section_id=?",
            (section_id,),
        )["c"]
        ungraded = _row(
            self.conn,
            """
            SELECT COUNT(*) AS c FROM submissions s
            LEFT JOIN grades g ON g.submission_id = s.submission_id
            WHERE s.section_id=? AND g.grade_id IS NULL
            """,
            (section_id,),
        )["c"]
        return {
            "section": sec,
            "metrics": {
                "active_enrollments": enrolled,
                "submissions": submitted,
                "ungraded": ungraded,
            },
        }

    def is_enrolled(self, user_id: str, section_id: str) -> bool:
        return (
            _row(
                self.conn,
                "SELECT enrollment_id FROM enrollments WHERE section_id=? AND user_id=? AND status='active'",
                (section_id, user_id),
            )
            is not None
        )

    def can_instruct(self, actor: Actor, section_id: str) -> bool:
        if actor.is_site_admin:
            sec = _row(self.conn, "SELECT site_id FROM sections WHERE section_id=?", (section_id,))
            return bool(sec and sec["site_id"] == actor.site_id)
        return (
            _row(
                self.conn,
                "SELECT user_id FROM section_instructors WHERE section_id=? AND user_id=?",
                (section_id, actor.actor_id),
            )
            is not None
        )

    def can_grade(self, actor: Actor, section_id: str) -> bool:
        if self.can_instruct(actor, section_id):
            return True
        return (
            _row(
                self.conn,
                "SELECT user_id FROM section_graders WHERE section_id=? AND user_id=?",
                (section_id, actor.actor_id),
            )
            is not None
        )

    def default_section_for_learner(self, actor: Actor) -> str | None:
        row = _row(
            self.conn,
            """
            SELECT e.section_id FROM enrollments e
            JOIN sections s ON s.section_id = e.section_id
            WHERE e.user_id=? AND e.status='active' AND s.site_id=?
            ORDER BY e.enrolled_at LIMIT 1
            """,
            (actor.actor_id, actor.site_id),
        )
        return row["section_id"] if row else None

    def _enrich(self, sec: dict[str, Any]) -> dict[str, Any]:
        meta = _row(self.conn, "SELECT * FROM section_runtime_metadata WHERE section_id=?", (sec["section_id"],))
        pkg = _row(self.conn, "SELECT * FROM packages WHERE package_id=?", (sec["package_id"],))
        instructors = [
            r["user_id"]
            for r in _rows(
                self.conn,
                "SELECT user_id FROM section_instructors WHERE section_id=?",
                (sec["section_id"],),
            )
        ]
        graders = [
            r["user_id"]
            for r in _rows(
                self.conn,
                "SELECT user_id FROM section_graders WHERE section_id=?",
                (sec["section_id"],),
            )
        ]
        return {
            **sec,
            "package": dict(pkg) if pkg else None,
            "runtime": dict(meta) if meta else None,
            "instructors": instructors,
            "graders": graders,
        }

    def _section_same_site(self, actor: Actor, section_id: str) -> sqlite3.Row:
        sec = _row(self.conn, "SELECT * FROM sections WHERE section_id=?", (section_id,))
        if not sec:
            raise ServiceError("SECTION_NOT_FOUND", 404)
        if sec["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        return sec

    def _require_admin_same_site(self, actor: Actor, section_id: str) -> sqlite3.Row:
        if not actor.is_site_admin:
            raise ServiceError("SITE_ADMIN_REQUIRED", 403)
        return self._section_same_site(actor, section_id)

    def _require_user_same_site(self, actor: Actor, user_id: str) -> sqlite3.Row:
        user = _row(self.conn, "SELECT * FROM users WHERE user_id=?", (user_id,))
        if not user:
            raise ServiceError("USER_NOT_FOUND", 404)
        if user["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_FORBIDDEN", 403)
        return user
