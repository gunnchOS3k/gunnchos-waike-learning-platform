"""Deterministic section gradebook (points, percentage, weighted categories)."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now, _row, _rows
from app.modules.sections import SectionService


def _finite(x: float) -> float:
    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf
        raise ServiceError("INVALID_POINTS", 400)
    return x


class GradebookService:
    def __init__(self, conn: sqlite3.Connection, sections: SectionService) -> None:
        self.conn = conn
        self.sections = sections

    def seed_for_section(self, section_id: str, assignment_id: str | None = None) -> None:
        now = _now()
        cat_id = f"gcat_{section_id}_assignments"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO gradebook_categories(category_id, section_id, name, weight, sort_order)
            VALUES (?,?,?,?,0)
            """,
            (cat_id, section_id, "Assignments", 1.0),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO gradebook_policies(section_id, late_penalty_pct, drop_lowest, missing_as_zero, updated_at)
            VALUES (?,?,0,1,?)
            """,
            (section_id, 0.0, now),
        )
        if assignment_id:
            item_id = f"gitem_{section_id}_{assignment_id}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO gradebook_items(
                  item_id, section_id, category_id, assignment_id, title, points_possible, due_at, created_at
                ) VALUES (?,?,?,?,?,?,NULL,?)
                """,
                (item_id, section_id, cat_id, assignment_id, "Week 01 assignment", 20.0, now),
            )
        self.conn.commit()

    def set_score(
        self,
        actor: Actor,
        item_id: str,
        learner_id: str,
        points_earned: float | None,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        item = _row(self.conn, "SELECT * FROM gradebook_items WHERE item_id=?", (item_id,))
        if not item:
            raise ServiceError("GRADEBOOK_ITEM_NOT_FOUND", 404)
        if not (
            self.sections.can_instruct(actor, item["section_id"])
            or self.sections.can_grade(actor, item["section_id"])
            or actor.is_site_admin
        ):
            raise ServiceError("FORBIDDEN", 403)
        if status not in {"graded", "ungraded", "missing", "late", "excused"}:
            raise ServiceError("INVALID_STATUS", 400)
        if points_earned is not None:
            points_earned = _finite(float(points_earned))
            if points_earned < 0 or points_earned > float(item["points_possible"]):
                raise ServiceError("POINTS_OUT_OF_RANGE", 400)
        if status == "graded" and points_earned is None:
            raise ServiceError("POINTS_REQUIRED", 400)
        if status in {"ungraded", "missing", "excused"}:
            # excused/missing/ungraded may clear points
            if status != "late":
                pass

        existing = _row(
            self.conn,
            "SELECT * FROM gradebook_score_entries WHERE item_id=? AND learner_id=?",
            (item_id, learner_id),
        )
        now = _now()
        before = dict(existing) if existing else None
        if existing:
            self.conn.execute(
                """
                UPDATE gradebook_score_entries
                SET points_earned=?, status=?, graded_by=?, graded_at=?, updated_at=?
                WHERE entry_id=?
                """,
                (points_earned, status, actor.actor_id, now, now, existing["entry_id"]),
            )
            entry_id = existing["entry_id"]
        else:
            entry_id = _id("gse")
            self.conn.execute(
                """
                INSERT INTO gradebook_score_entries(
                  entry_id, item_id, learner_id, points_earned, status, graded_by, graded_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (entry_id, item_id, learner_id, points_earned, status, actor.actor_id, now, now),
            )
        after = dict(_row(self.conn, "SELECT * FROM gradebook_score_entries WHERE entry_id=?", (entry_id,)))
        if reason.strip() or before is not None:
            self.conn.execute(
                """
                INSERT INTO grade_override_audits(override_id, entry_id, actor_id, reason, before_json, after_json, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    _id("goa"),
                    entry_id,
                    actor.actor_id,
                    reason or "grade_set",
                    json.dumps(before) if before else None,
                    json.dumps(after),
                    now,
                ),
            )
        _audit(self.conn, actor.actor_id, "gradebook_set", "gradebook_entry", entry_id, {"status": status})
        self.conn.commit()
        return after

    def sync_from_assessment_grade(
        self,
        actor: Actor,
        section_id: str,
        assignment_id: str,
        learner_id: str,
        points_earned: float,
        points_possible: float,
    ) -> None:
        item = _row(
            self.conn,
            "SELECT * FROM gradebook_items WHERE section_id=? AND assignment_id=?",
            (section_id, assignment_id),
        )
        if not item:
            return
        # Scale assessment points into item points_possible if needed
        possible = float(item["points_possible"])
        scaled = 0.0 if points_possible <= 0 else (points_earned / points_possible) * possible
        self.set_score(actor, item["item_id"], learner_id, _finite(scaled), "graded", reason="assessment_sync")

    def matrix(self, actor: Actor, section_id: str) -> dict[str, Any]:
        if not (
            self.sections.can_instruct(actor, section_id)
            or self.sections.can_grade(actor, section_id)
            or actor.is_site_admin
        ):
            raise ServiceError("FORBIDDEN", 403)
        self.sections._section_same_site(actor, section_id)
        return self._compute_matrix(section_id)

    def learner_view(self, actor: Actor, section_id: str) -> dict[str, Any]:
        if actor.role.value != "learner" and not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        if not self.sections.is_enrolled(actor.actor_id, section_id):
            raise ServiceError("NOT_ENROLLED", 403)
        full = self._compute_matrix(section_id)
        # Filter to own scores
        own_rows = [r for r in full["rows"] if r["learner_id"] == actor.actor_id]
        return {
            "section_id": section_id,
            "categories": full["categories"],
            "items": full["items"],
            "policy": full["policy"],
            "rows": own_rows,
        }

    def _compute_matrix(self, section_id: str) -> dict[str, Any]:
        categories = [
            dict(r)
            for r in _rows(
                self.conn,
                "SELECT * FROM gradebook_categories WHERE section_id=? ORDER BY sort_order, name",
                (section_id,),
            )
        ]
        items = [
            dict(r)
            for r in _rows(
                self.conn,
                "SELECT * FROM gradebook_items WHERE section_id=? ORDER BY created_at",
                (section_id,),
            )
        ]
        policy_row = _row(self.conn, "SELECT * FROM gradebook_policies WHERE section_id=?", (section_id,))
        policy = dict(policy_row) if policy_row else {
            "section_id": section_id,
            "late_penalty_pct": 0.0,
            "drop_lowest": 0,
            "missing_as_zero": 1,
        }
        learners = [
            dict(r)
            for r in _rows(
                self.conn,
                """
                SELECT u.user_id AS learner_id, u.display_name, u.username
                FROM enrollments e
                JOIN users u ON u.user_id = e.user_id
                WHERE e.section_id=? AND e.status='active'
                ORDER BY u.username
                """,
                (section_id,),
            )
        ]
        entries = {
            (r["item_id"], r["learner_id"]): dict(r)
            for r in _rows(
                self.conn,
                """
                SELECT e.* FROM gradebook_score_entries e
                JOIN gradebook_items i ON i.item_id = e.item_id
                WHERE i.section_id=?
                """,
                (section_id,),
            )
        }

        rows_out: list[dict[str, Any]] = []
        for learner in learners:
            lid = learner["learner_id"]
            cell_map: dict[str, Any] = {}
            cat_scores: dict[str, list[float | None]] = {c["category_id"]: [] for c in categories}
            for item in items:
                key = (item["item_id"], lid)
                entry = entries.get(key)
                if entry is None:
                    status = "ungraded"
                    pts = None
                    if int(policy.get("missing_as_zero") or 0) == 1:
                        # Treat never-scored as missing (0) only when computing finals after due;
                        # for display keep ungraded.
                        status = "ungraded"
                        pts = None
                else:
                    status = entry["status"]
                    pts = entry["points_earned"]
                    if status == "late" and pts is not None:
                        pen = float(policy.get("late_penalty_pct") or 0)
                        pts = max(0.0, float(pts) * (1.0 - pen / 100.0))
                    if status == "excused":
                        pts = None  # excluded from category average
                    if status == "missing":
                        pts = 0.0 if int(policy.get("missing_as_zero") or 0) else None

                possible = float(item["points_possible"])
                pct = None
                if pts is not None and possible > 0:
                    pct = _finite(float(pts) / possible * 100.0)
                cell_map[item["item_id"]] = {
                    "item_id": item["item_id"],
                    "points_earned": pts,
                    "points_possible": possible,
                    "percent": pct,
                    "status": status,
                }
                if status != "excused":
                    # Contribution ratio 0..1 for category weight
                    if pts is None:
                        cat_scores[item["category_id"]].append(None)
                    else:
                        cat_scores[item["category_id"]].append(_finite(float(pts) / possible))

            category_results = []
            weighted_sum = 0.0
            weight_total = 0.0
            for cat in categories:
                scores = [s for s in cat_scores[cat["category_id"]] if s is not None]
                # drop_lowest
                drop = int(policy.get("drop_lowest") or 0)
                if drop > 0 and len(scores) > drop:
                    scores = sorted(scores)[drop:]
                if not scores:
                    cat_pct = None
                else:
                    cat_pct = _finite(sum(scores) / len(scores) * 100.0)
                w = float(cat["weight"])
                category_results.append(
                    {
                        "category_id": cat["category_id"],
                        "name": cat["name"],
                        "weight": w,
                        "percent": cat_pct,
                    }
                )
                if cat_pct is not None and w > 0:
                    weighted_sum += cat_pct * w
                    weight_total += w

            overall = None
            if weight_total > 0:
                overall = _finite(weighted_sum / weight_total)
            # Guard NaN
            if overall is not None and (math.isnan(overall) or math.isinf(overall)):
                raise ServiceError("GRADEBOOK_NAN", 500)

            rows_out.append(
                {
                    **learner,
                    "cells": cell_map,
                    "categories": category_results,
                    "overall_percent": overall,
                }
            )

        return {
            "section_id": section_id,
            "categories": categories,
            "items": items,
            "policy": policy,
            "rows": rows_out,
        }

    def override_audits(self, actor: Actor, entry_id: str) -> list[dict[str, Any]]:
        entry = _row(self.conn, "SELECT * FROM gradebook_score_entries WHERE entry_id=?", (entry_id,))
        if not entry:
            raise ServiceError("GRADEBOOK_ENTRY_NOT_FOUND", 404)
        item = _row(self.conn, "SELECT * FROM gradebook_items WHERE item_id=?", (entry["item_id"],))
        assert item is not None
        if not (
            self.sections.can_instruct(actor, item["section_id"])
            or actor.is_site_admin
        ):
            raise ServiceError("FORBIDDEN", 403)
        return [
            dict(r)
            for r in _rows(
                self.conn,
                "SELECT * FROM grade_override_audits WHERE entry_id=? ORDER BY created_at",
                (entry_id,),
            )
        ]
