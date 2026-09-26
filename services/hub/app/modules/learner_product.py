"""Additive learner product aggregations. Reuses sections/assessment; no second LMS."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row, _rows


ANSWER_KEY_MARKERS = (
    "answer_key",
    "answer-key",
    "answer keys",
    "instructor_solution",
    "instructor-only",
    "solution_guide",
)


def _is_answer_key(title: str, snippet: str = "") -> bool:
    blob = f"{title} {snippet}".lower()
    return any(m in blob for m in ANSWER_KEY_MARKERS)


class LearnerProductService:
    def __init__(self, conn: sqlite3.Connection, sections: Any, assessment: Any) -> None:
        self.conn = conn
        self.sections = sections
        self.assessment = assessment

    def search(self, actor: Actor, query: str) -> dict[str, Any]:
        q = (query or "").strip().lower()
        if not q:
            return {"hits": []}
        allowed = {s["section_id"] for s in self.sections.list_sections_for_actor(actor)}
        hits: list[dict[str, Any]] = []
        for sec in self.sections.list_sections_for_actor(actor):
            blob = f"{sec.get('title','')} {sec.get('code','')}"
            if q in blob.lower():
                hits.append(
                    {
                        "id": sec["section_id"],
                        "kind": "course",
                        "title": sec.get("title") or sec.get("code"),
                        "snippet": sec.get("code") or "",
                        "section_id": sec["section_id"],
                    }
                )
        try:
            assignments = self.assessment.list_assignments(actor)
        except Exception:
            assignments = []
        for a in assignments:
            title = a.get("title") or ""
            snippet = a.get("module_id") or ""
            if _is_answer_key(title, snippet) and actor.role in {Role.LEARNER, Role.GUARDIAN}:
                continue
            if q not in f"{title} {snippet}".lower():
                continue
            section_id = a.get("section_id") or next(iter(allowed), "")
            if section_id and section_id not in allowed:
                continue
            hits.append(
                {
                    "id": a.get("assignment_id"),
                    "kind": "assignment",
                    "title": title,
                    "snippet": snippet,
                    "section_id": section_id,
                }
            )
        return {"hits": hits}

    def notifications(self, actor: Actor) -> list[dict[str, Any]]:
        reads = {
            r["notice_id"]
            for r in _rows(
                self.conn,
                "SELECT notice_id FROM learner_notification_reads WHERE user_id=?",
                (actor.actor_id,),
            )
        }
        out: list[dict[str, Any]] = []
        for sec in self.sections.list_sections_for_actor(actor):
            notes = sec.get("publish_notes") or ""
            if notes:
                nid = f"ann:{sec['section_id']}"
                out.append(
                    {
                        "id": nid,
                        "kind": "announcement",
                        "title": sec.get("title") or "Course update",
                        "body": notes,
                        "created_at": sec.get("created_at") or _now(),
                        "deep_link": f"waike://course/{sec['section_id']}",
                        "unread": nid not in reads,
                    }
                )
        return out

    def mark_read(self, actor: Actor, notice_id: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO learner_notification_reads(read_id, user_id, notice_id, read_at)
            VALUES (?,?,?,?)
            """,
            (_id("nrd"), actor.actor_id, notice_id, _now()),
        )
        self.conn.commit()

    def announcements(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        sec = self.sections.get_section(actor, section_id)
        notes = sec.get("publish_notes") or ""
        if not notes:
            return []
        return [
            {
                "id": f"ann:{section_id}",
                "title": "Course announcement",
                "body": notes,
                "created_at": sec.get("created_at") or _now(),
            }
        ]

    def modules(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        self.sections.get_section(actor, section_id)
        return [
            {
                "id": f"{section_id}:w01",
                "title": "Week 1",
                "order": 1,
                "status": "not_started",
                "lesson": "Lesson 1",
            }
        ]

    def copy_section(self, actor: Actor, body: dict[str, Any]) -> dict[str, Any]:
        source_id = body["source_section_id"]
        if not (actor.is_site_admin or self.sections.can_instruct(actor, source_id)):
            raise ServiceError("FORBIDDEN", 403)
        source = self.sections.get_section(actor, source_id)
        package_id = source.get("package_id")
        if not package_id:
            raise ServiceError("PACKAGE_NOT_FOUND", 404)
        now = _now()
        section_id = _id("sec")
        self.conn.execute(
            """
            INSERT INTO sections(section_id, site_id, package_id, code, title, published, created_at)
            VALUES (?,?,?,?,?,0,?)
            """,
            (section_id, actor.site_id, package_id, body["code"], body["title"], now),
        )
        self.conn.execute(
            "INSERT INTO section_runtime_metadata(section_id, due_override_json, publish_notes, updated_at) VALUES (?,?,?,?)",
            (section_id, "{}", body.get("term") or "", now),
        )
        instructor_id = body.get("instructor_id") or actor.actor_id
        self.conn.execute(
            "INSERT OR IGNORE INTO section_instructors(section_id, user_id, assigned_at) VALUES (?,?,?)",
            (section_id, instructor_id, now),
        )
        _audit(self.conn, actor.actor_id, "copy_section", "section", section_id, {"source": source_id})
        self.conn.commit()
        return {"section_id": section_id, "package_id": package_id, "duplicated_curriculum": False}

    def preview_due_shift(self, actor: Actor, section_id: str, delta_hours: int) -> dict[str, Any]:
        if not (self.sections.can_instruct(actor, section_id) or actor.is_site_admin):
            raise ServiceError("FORBIDDEN", 403)
        items = _rows(
            self.conn,
            "SELECT item_id, title, due_at FROM gradebook_items WHERE section_id=?",
            (section_id,),
        )
        preview = []
        for row in items:
            current = row["due_at"]
            proposed = None
            if current:
                try:
                    dt = datetime.fromisoformat(str(current).replace("Z", "+00:00"))
                    proposed = (dt + timedelta(hours=delta_hours)).isoformat()
                except ValueError:
                    proposed = None
            preview.append(
                {
                    "id": row["item_id"],
                    "title": row["title"],
                    "current_due": current,
                    "proposed_due": proposed,
                }
            )
        return {"items": preview}

    def apply_due_shift(self, actor: Actor, section_id: str, delta_hours: int) -> dict[str, Any]:
        preview = self.preview_due_shift(actor, section_id, delta_hours)
        count = 0
        for item in preview["items"]:
            if not item["proposed_due"]:
                continue
            self.conn.execute(
                "UPDATE gradebook_items SET due_at=? WHERE item_id=?",
                (item["proposed_due"], item["id"]),
            )
            count += 1
        self.conn.execute(
            """
            INSERT INTO due_shift_events(event_id, section_id, actor_id, delta_hours, preview_json, applied, created_at)
            VALUES (?,?,?,?,?,1,?)
            """,
            (_id("shift"), section_id, actor.actor_id, delta_hours, json.dumps(preview), _now()),
        )
        self.conn.commit()
        return {"applied": True, "count": count}

    def list_comments(self, actor: Actor) -> list[dict[str, Any]]:
        if not actor.is_instructor_side:
            raise ServiceError("STAFF_REQUIRED", 403)
        return [
            dict(r)
            for r in _rows(
                self.conn,
                "SELECT comment_id, title, body FROM comment_bank WHERE owner_user_id=? AND site_id=? ORDER BY created_at",
                (actor.actor_id, actor.site_id),
            )
        ]

    def upsert_comment(self, actor: Actor, title: str, body: str) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("STAFF_REQUIRED", 403)
        cid = _id("cmt")
        self.conn.execute(
            "INSERT INTO comment_bank(comment_id, owner_user_id, site_id, title, body, created_at) VALUES (?,?,?,?,?,?)",
            (cid, actor.actor_id, actor.site_id, title, body, _now()),
        )
        self.conn.commit()
        return {"comment_id": cid, "title": title, "body": body}

    def intervention(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        if not (self.sections.can_instruct(actor, section_id) or actor.is_site_admin):
            raise ServiceError("FORBIDDEN", 403)
        roster = self.sections.roster(actor, section_id)
        out = []
        for row in roster:
            missing = _row(
                self.conn,
                """
                SELECT COUNT(*) AS n FROM gradebook_items gi
                WHERE gi.section_id=? AND NOT EXISTS (
                  SELECT 1 FROM submissions s WHERE s.learner_id=? AND s.assignment_id=gi.assignment_id
                )
                """,
                (section_id, row["user_id"]),
            )
            waiting = _row(
                self.conn,
                """
                SELECT COUNT(*) AS n FROM submissions s
                WHERE s.learner_id=? AND s.section_id=? AND s.status='submitted'
                """,
                (row["user_id"], section_id),
            )
            signals = []
            if missing and int(missing["n"] or 0) > 0:
                signals.append("missing_work")
            if not signals:
                continue
            out.append(
                {
                    "learner_id": row["user_id"],
                    "display_name": row.get("display_name") or row["user_id"],
                    "signals": signals,
                    "waiting_for_instructor_grade": bool(waiting and int(waiting["n"] or 0) > 0),
                }
            )
        return out

    def mlv_summary(self, actor: Actor) -> dict[str, Any]:
        sections = self.sections.list_sections_for_actor(actor)
        return {
            "display_name": actor.display_name,
            "continue_learning": {"title": sections[0]["title"]} if sections else None,
            "due_soon": [],
            "courses": [{"section_id": s["section_id"], "title": s.get("title")} for s in sections],
            "recent_feedback_count": 0,
            "upcoming_count": 0,
            "contract": "WAIKE_MLV_EDUCATION_CONTRACT.v1",
        }

    def list_school_apps(self, actor: Actor) -> list[dict[str, Any]]:
        rows = _rows(self.conn, "SELECT * FROM school_apps WHERE site_id=?", (actor.site_id,))
        return [
            {
                "app_id": r["app_id"],
                "label": r["label"],
                "launch_kind": r["launch_kind"],
                "url": r["url"],
                "allowed_origins": json.loads(r["allowed_origins_json"] or "[]"),
                "pinned": bool(r["pinned"]),
                "configured_by": "institution",
                "captures_credentials": False,
            }
            for r in rows
        ]

    def pin_school_app(self, actor: Actor, app_id: str, pinned: bool) -> None:
        row = _row(self.conn, "SELECT * FROM school_apps WHERE app_id=? AND site_id=?", (app_id, actor.site_id))
        if not row:
            raise ServiceError("APP_NOT_FOUND", 404)
        self.conn.execute("UPDATE school_apps SET pinned=? WHERE app_id=?", (1 if pinned else 0, app_id))
        self.conn.commit()

    @staticmethod
    def validate_school_app_url(url: str, allowed_origins: list[str]) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin in allowed_origins
