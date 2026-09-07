"""Gate A activity engine: quizzes, labs, discussions, groups, accommodations, grading efficiency.

Every entry point resolves the owning section and authorizes against *that* section via
``SectionService``. Holding an instructor role in the same site is not authorization.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError
from app.modules.lab_runner import LabRunnerError, resolve_runner, run_local_software
from app.modules.sections import SectionService
from app.modules import txn

LAB_MODES = frozenset(
    {
        "LOCAL_SOFTWARE",
        "REPO_CONNECTED",
        "DEVICE_HARDWARE_ASSISTED",
        "MANUAL_EVIDENCE",
    }
)
QUIZ_ITEM_TYPES = frozenset(
    {
        "single_choice",
        "multi_select",
        "true_false",
        "short_response",
        "numeric",
        "file_response",
    }
)

# Small, explicit allowance for network/render latency between the learner pressing
# submit and the request landing. Not a second chance at the quiz.
SERVER_GRACE_SECONDS = 30

# The demo section predates section-scoped seed ids and keeps its original ones.
LEGACY_SEED_SECTION = "sec_alpha_dc_w01"

OPEN_ATTEMPT_STATES = frozenset({"in_progress"})
GRADABLE_ATTEMPT_STATES = frozenset({"submitted", "graded", "timed_out"})


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ActivityEngine:
    def __init__(self, conn: sqlite3.Connection, sections: SectionService | None = None) -> None:
        self.conn = conn
        self.sections = sections or SectionService(conn)

    # --- authorization helpers ------------------------------------------------

    def _audit(
        self, actor: Actor, action: str, entity_type: str, entity_id: str, detail: dict[str, Any]
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO audit_events(
              event_id, actor_id, action, entity_type, entity_id, detail_json, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (_id("aud"), actor.actor_id, action, entity_type, entity_id, json.dumps(detail), _now()),
        )

    def _quiz(self, quiz_id: str) -> sqlite3.Row:
        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        if not quiz:
            raise ServiceError("QUIZ_NOT_FOUND", 404)
        return quiz

    def _attempt(self, attempt_id: str) -> sqlite3.Row:
        attempt = self.conn.execute(
            "SELECT * FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if not attempt:
            raise ServiceError("ATTEMPT_NOT_FOUND", 404)
        return attempt

    def _lab(self, lab_id: str) -> sqlite3.Row:
        lab = self.conn.execute(
            "SELECT * FROM lab_definitions WHERE lab_id=?", (lab_id,)
        ).fetchone()
        if not lab:
            raise ServiceError("LAB_NOT_FOUND", 404)
        return lab

    # --- seed helpers for tests ----------------------------------------------

    def seed_section_activities(
        self, *, section_id: str, site_id: str, instructor_id: str
    ) -> dict[str, Any]:
        # Every seeded id is section-scoped so two sections never share a quiz,
        # an item or a lab. The original demo section keeps its historical ids.
        legacy = section_id == LEGACY_SEED_SECTION
        quiz_id = "quiz_dc_w01_gate_a" if legacy else f"quiz_dc_w01_{section_id}"
        lab_id = "lab_dc_local_software" if legacy else f"lab_dc_local_software_{section_id}"

        def item(base: str) -> str:
            return base if legacy else f"{base}_{section_id}"

        existing = self.conn.execute(
            "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=? AND section_id=?",
            (quiz_id, section_id),
        ).fetchone()
        if existing:
            lab = self.conn.execute(
                "SELECT lab_id FROM lab_definitions WHERE section_id=? LIMIT 1", (section_id,)
            ).fetchone()
            return {"quiz_id": quiz_id, "lab_id": lab["lab_id"] if lab else None}

        policies = {
            "availability_start": None,
            "availability_end": None,
            "attempt_limit": 2,
            "time_limit_minutes": 30,
            "autosave": True,
            "offline_eligible": True,
            "answer_visibility": "after_return",
            "feedback_mode": "delayed",
            "anonymous_grading": False,
        }
        answer_key = {
            item("qi_sc"): {"correct": ["b"]},
            item("qi_ms"): {"correct": ["a", "c"]},
            item("qi_tf"): {"correct": True},
            item("qi_num"): {"correct": 42, "tolerance": 0},
            item("qi_short"): {"correct_normalized": "digital confidence"},
        }
        self.conn.execute(
            """
            INSERT INTO quiz_definitions(
              quiz_id, section_id, site_id, title, policies_json, answer_key_json,
              offline_eligible, high_integrity_timed, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                quiz_id,
                section_id,
                site_id,
                "Gate A Digital Confidence Quiz",
                json.dumps(policies),
                json.dumps(answer_key),
                1,
                0,
                instructor_id,
                _now(),
            ),
        )
        items = [
            ("qi_sc", 1, "single_choice", "Primary trust signal?", ["a", "b", "c"], 1.0, "objective"),
            ("qi_ms", 2, "multi_select", "Select all safe practices", ["a", "b", "c"], 2.0, "objective"),
            ("qi_tf", 3, "true_false", "Receipts are immutable", [], 1.0, "objective"),
            ("qi_num", 4, "numeric", "Answer to life?", [], 1.0, "objective"),
            ("qi_short", 5, "short_response", "Module theme?", [], 1.0, "objective"),
            ("qi_file", 6, "file_response", "Upload reflection", [], 2.0, "manual"),
        ]
        for item_id, ord_, typ, prompt, opts, pts, mode in items:
            self.conn.execute(
                """
                INSERT INTO quiz_items(
                  item_id, quiz_id, ordinal, item_type, prompt, options_json, max_points, grading_mode
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (item(item_id), quiz_id, ord_, typ, prompt, json.dumps(opts), pts, mode),
            )

        self.conn.execute(
            """
            INSERT INTO lab_definitions(
              lab_id, section_id, site_id, title, mode, spec_json, runner_id,
              offline_eligible, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lab_id,
                section_id,
                site_id,
                "Local hash lab",
                "LOCAL_SOFTWARE",
                json.dumps(
                    {
                        "required_capabilities": ["local_python"],
                        "environment": {
                            "sandbox": True,
                            "workdir": "ephemeral",
                            "time_limit_s": 15,
                            "network": False,
                        },
                        "steps": ["provide input text", "server runs trusted fixture", "record digest"],
                        "expected_evidence": ["stdout_sha256", "input_sha256"],
                        "grading_mode": "manual",
                        "offline_eligible": True,
                        "safety_notes": [
                            "learner supplies data only; command and interpreter are server-fixed",
                            "process-level confinement, not an OS sandbox",
                        ],
                    }
                ),
                "python_hash_fixture_v1",
                1,
                instructor_id,
                _now(),
            ),
        )
        txn.commit(self.conn)
        return {"quiz_id": quiz_id, "lab_id": lab_id}

    # --- accommodations ------------------------------------------------------

    def upsert_accommodation(
        self,
        actor: Actor,
        *,
        learner_id: str,
        section_id: str,
        time_multiplier: float | None = None,
        availability_extension_minutes: int | None = None,
        attempt_override: int | None = None,
        due_extension_minutes: int | None = None,
        alternate_modality: str | None = None,
        notes_private: str | None = None,
    ) -> dict[str, Any]:
        self.sections.require_staff_scope(actor, section_id)
        if not self.sections.is_enrolled(learner_id, section_id):
            raise ServiceError("LEARNER_NOT_ENROLLED", 404)
        if time_multiplier is not None and (
            time_multiplier <= 0 or not math.isfinite(float(time_multiplier))
        ):
            raise ServiceError("INVALID_TIME_MULTIPLIER", 400)
        if attempt_override is not None and attempt_override <= 0:
            raise ServiceError("INVALID_ATTEMPT_OVERRIDE", 400)
        if due_extension_minutes is not None and due_extension_minutes < 0:
            raise ServiceError("INVALID_DUE_EXTENSION", 400)

        existing = self.conn.execute(
            "SELECT * FROM accommodations WHERE learner_id=? AND section_id=?",
            (learner_id, section_id),
        ).fetchone()
        before = dict(existing) if existing else None
        now = _now()
        if existing:
            self.conn.execute(
                """
                UPDATE accommodations SET
                  time_multiplier=?, availability_extension_minutes=?, attempt_override=?,
                  due_extension_minutes=?, alternate_modality=?, notes_private=?,
                  updated_at=?, active=1
                WHERE accommodation_id=?
                """,
                (
                    time_multiplier,
                    availability_extension_minutes,
                    attempt_override,
                    due_extension_minutes,
                    alternate_modality,
                    notes_private,
                    now,
                    existing["accommodation_id"],
                ),
            )
            acc_id = existing["accommodation_id"]
        else:
            acc_id = _id("acc")
            self.conn.execute(
                """
                INSERT INTO accommodations(
                  accommodation_id, learner_id, section_id, site_id, time_multiplier,
                  availability_extension_minutes, attempt_override, due_extension_minutes,
                  alternate_modality, notes_private, created_by, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    acc_id,
                    learner_id,
                    section_id,
                    actor.site_id,
                    time_multiplier,
                    availability_extension_minutes,
                    attempt_override,
                    due_extension_minutes,
                    alternate_modality,
                    notes_private,
                    actor.actor_id,
                    now,
                    now,
                ),
            )
        after = dict(
            self.conn.execute(
                "SELECT * FROM accommodations WHERE accommodation_id=?", (acc_id,)
            ).fetchone()
        )
        self._audit(
            actor,
            "accommodation_upsert",
            "accommodation",
            acc_id,
            {
                "learner_id": learner_id,
                "section_id": section_id,
                # Private notes stay out of the audit body; presence is still recorded.
                "before": _redact_accommodation(before),
                "after": _redact_accommodation(after),
            },
        )
        txn.commit(self.conn)
        return self.get_accommodation(actor, learner_id, section_id)

    def get_accommodation(self, actor: Actor, learner_id: str, section_id: str) -> dict[str, Any]:
        # Peers must never see accommodation details, private or applied.
        self.sections.require_learner_or_staff_for(actor, section_id, learner_id)
        row = self.conn.execute(
            "SELECT * FROM accommodations WHERE learner_id=? AND section_id=? AND active=1",
            (learner_id, section_id),
        ).fetchone()
        if not row:
            raise ServiceError("ACCOMMODATION_NOT_FOUND", 404)
        data = dict(row)
        if actor.actor_id == learner_id and not self.sections.has_staff_scope(actor, section_id):
            # Learner sees applied effects, not private staff notes.
            data.pop("notes_private", None)
        return data

    def peer_cannot_read_accommodation(self, peer: Actor, learner_id: str, section_id: str) -> bool:
        try:
            self.get_accommodation(peer, learner_id, section_id)
            return False
        except ServiceError as e:
            return e.status == 403

    def _effective_policies(self, quiz_id: str, learner_id: str, section_id: str) -> dict[str, Any]:
        quiz = self._quiz(quiz_id)
        policies = json.loads(quiz["policies_json"])
        acc = self.conn.execute(
            "SELECT * FROM accommodations WHERE learner_id=? AND section_id=? AND active=1",
            (learner_id, section_id),
        ).fetchone()
        if acc:
            if acc["attempt_override"] is not None:
                policies["attempt_limit"] = int(acc["attempt_override"])
            if acc["time_multiplier"] is not None and policies.get("time_limit_minutes"):
                policies["time_limit_minutes"] = float(policies["time_limit_minutes"]) * float(
                    acc["time_multiplier"]
                )
            if acc["availability_extension_minutes"] and policies.get("availability_end"):
                end = _parse(policies["availability_end"]) + timedelta(
                    minutes=int(acc["availability_extension_minutes"])
                )
                policies["availability_end"] = _fmt(end)
            # due_extension_minutes: extend availability due-window when present, and
            # add absolute minutes to the timed attempt deadline (submission due).
            if acc["due_extension_minutes"] is not None:
                due_ext = int(acc["due_extension_minutes"])
                if due_ext > 0:
                    if policies.get("availability_end"):
                        end = _parse(policies["availability_end"]) + timedelta(minutes=due_ext)
                        policies["availability_end"] = _fmt(end)
                    if policies.get("time_limit_minutes") is not None:
                        policies["time_limit_minutes"] = float(policies["time_limit_minutes"]) + float(
                            due_ext
                        )
                    policies["due_extension_minutes_applied"] = due_ext
            policies["accommodation_applied"] = True
            policies["alternate_modality"] = acc["alternate_modality"]
        else:
            policies["accommodation_applied"] = False
        return policies

    # --- quizzes -------------------------------------------------------------

    def learner_quiz_view(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        quiz = self._quiz(quiz_id)
        self.sections.require_section_access(actor, quiz["section_id"])
        items = self.conn.execute(
            "SELECT item_id, ordinal, item_type, prompt, options_json, max_points, grading_mode "
            "FROM quiz_items WHERE quiz_id=? ORDER BY ordinal",
            (quiz_id,),
        ).fetchall()
        # Answer keys NEVER returned on the learner path.
        return {
            "quiz_id": quiz_id,
            "title": quiz["title"],
            "section_id": quiz["section_id"],
            "offline_eligible": bool(quiz["offline_eligible"]),
            "high_integrity_timed": bool(quiz["high_integrity_timed"]),
            "policies": self._effective_policies(quiz_id, actor.actor_id, quiz["section_id"])
            if actor.is_learner
            else json.loads(quiz["policies_json"]),
            "items": [
                {
                    "item_id": i["item_id"],
                    "ordinal": i["ordinal"],
                    "item_type": i["item_type"],
                    "prompt": i["prompt"],
                    "options": json.loads(i["options_json"] or "[]"),
                    "max_points": i["max_points"],
                    "grading_mode": i["grading_mode"],
                }
                for i in items
            ],
        }

    def instructor_answer_key(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        quiz = self._quiz(quiz_id)
        self.sections.require_staff_scope(actor, quiz["section_id"])
        return {"quiz_id": quiz_id, "answer_key": json.loads(quiz["answer_key_json"])}

    def start_quiz_attempt(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        quiz = self._quiz(quiz_id)
        self.sections.require_learner_enrollment(actor, quiz["section_id"])
        policies = self._effective_policies(quiz_id, actor.actor_id, quiz["section_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE quiz_id=? AND learner_id=?",
            (quiz_id, actor.actor_id),
        ).fetchone()["c"]
        limit = int(policies.get("attempt_limit") or 1)
        if count >= limit:
            raise ServiceError("ATTEMPT_LIMIT", 403)
        now = datetime.now(tz=timezone.utc)
        if policies.get("availability_start") and now < _parse(policies["availability_start"]):
            raise ServiceError("NOT_AVAILABLE", 403)
        if policies.get("availability_end") and now > _parse(policies["availability_end"]):
            raise ServiceError("NOT_AVAILABLE", 403)

        # Deadline is server start + accommodated duration; the client never supplies it.
        limit_minutes = policies.get("time_limit_minutes")
        deadline = (
            now + timedelta(minutes=float(limit_minutes)) if limit_minutes is not None else None
        )
        attempt_id = _id("qatt")
        self.conn.execute(
            """
            INSERT INTO quiz_attempts(
              attempt_id, quiz_id, learner_id, section_id, site_id, attempt_number,
              started_at, deadline_at, effective_time_limit_minutes, status, accommodation_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                attempt_id,
                quiz_id,
                actor.actor_id,
                quiz["section_id"],
                quiz["site_id"],
                count + 1,
                _fmt(now),
                _fmt(deadline) if deadline else None,
                float(limit_minutes) if limit_minutes is not None else None,
                "in_progress",
                json.dumps({"applied": policies.get("accommodation_applied", False)}),
            ),
        )
        txn.commit(self.conn)
        return {
            "attempt_id": attempt_id,
            "attempt_number": count + 1,
            "started_at": _fmt(now),
            "deadline_at": _fmt(deadline) if deadline else None,
            "time_limit_minutes": limit_minutes,
            "server_grace_seconds": SERVER_GRACE_SECONDS,
            "status": "in_progress",
        }

    def submit_quiz_attempt(
        self,
        actor: Actor,
        attempt_id: str,
        responses: dict[str, Any],
        *,
        client_mutation_id: str | None = None,
        client_elapsed_minutes: float | None = None,
    ) -> dict[str, Any]:
        if client_mutation_id:
            existing = self.conn.execute(
                "SELECT * FROM quiz_attempts WHERE client_mutation_id=? AND learner_id=?",
                (client_mutation_id, actor.actor_id),
            ).fetchone()
            if existing and existing["status"] in GRADABLE_ATTEMPT_STATES | {"returned"}:
                return self._attempt_result(existing["attempt_id"])

        attempt = self._attempt(attempt_id)
        if attempt["learner_id"] != actor.actor_id:
            raise ServiceError("ATTEMPT_NOT_FOUND", 404)
        self.sections.require_learner_enrollment(actor, attempt["section_id"])
        if attempt["status"] not in OPEN_ATTEMPT_STATES:
            raise ServiceError("ATTEMPT_NOT_OPEN", 400)

        now = datetime.now(tz=timezone.utc)
        deadline = _parse(attempt["deadline_at"]) if attempt["deadline_at"] else None
        # Server clock is authoritative. A client-reported elapsed time is advisory only:
        # recorded for proctoring signal, never used to accept or reject the submission.
        timed_out = bool(deadline and now > deadline + timedelta(seconds=SERVER_GRACE_SECONDS))
        client_claim = (
            {
                "client_elapsed_minutes": float(client_elapsed_minutes),
                "server_elapsed_minutes": round(
                    (now - _parse(attempt["started_at"])).total_seconds() / 60.0, 4
                ),
                "trusted": False,
            }
            if client_elapsed_minutes is not None
            else None
        )

        quiz = self._quiz(attempt["quiz_id"])
        answer_key = json.loads(quiz["answer_key_json"])
        items = self.conn.execute(
            "SELECT * FROM quiz_items WHERE quiz_id=? ORDER BY ordinal", (attempt["quiz_id"],)
        ).fetchall()

        score = 0.0
        max_score = 0.0
        manual_items: list[str] = []
        for item in items:
            max_score += float(item["max_points"])
            resp = responses.get(item["item_id"])
            self.conn.execute(
                """
                INSERT INTO quiz_responses(
                  response_id, attempt_id, item_id, response_json, points_earned, auto_graded
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(attempt_id, item_id) DO UPDATE SET
                  response_json=excluded.response_json,
                  points_earned=excluded.points_earned,
                  auto_graded=excluded.auto_graded
                """,
                (_id("qresp"), attempt_id, item["item_id"], json.dumps(resp), None, 0),
            )
            if item["grading_mode"] == "manual":
                manual_items.append(item["item_id"])
                continue
            if timed_out:
                # Late work is retained as evidence but never auto-scored as valid work.
                continue
            pts = self._grade_objective(item, resp, answer_key.get(item["item_id"], {}))
            score += pts
            self.conn.execute(
                "UPDATE quiz_responses SET points_earned=?, auto_graded=1 "
                "WHERE attempt_id=? AND item_id=?",
                (pts, attempt_id, item["item_id"]),
            )

        if timed_out:
            status = "timed_out"
            stored_score: float | None = None
        else:
            status = "graded" if not manual_items else "submitted"
            stored_score = score

        accommodation = json.loads(attempt["accommodation_json"] or "{}")
        if client_claim:
            accommodation["client_elapsed_claim"] = client_claim
        self.conn.execute(
            """
            UPDATE quiz_attempts SET
              submitted_at=?, status=?, score=?, max_score=?, server_timed_out=?,
              accommodation_json=?, client_mutation_id=COALESCE(?, client_mutation_id)
            WHERE attempt_id=?
            """,
            (
                _fmt(now),
                status,
                stored_score,
                max_score,
                1 if timed_out else 0,
                json.dumps(accommodation),
                client_mutation_id,
                attempt_id,
            ),
        )
        txn.commit(self.conn)
        return {
            "attempt_id": attempt_id,
            "status": status,
            "score": stored_score,
            "max_score": max_score,
            "manual_items": manual_items,
            "server_timed_out": timed_out,
            "deadline_at": attempt["deadline_at"],
            "submitted_at": _fmt(now),
            "client_elapsed_claim": client_claim,
            "answer_key_exposed": False,
        }

    def _grade_objective(self, item: sqlite3.Row, resp: Any, key: dict[str, Any]) -> float:
        typ = item["item_type"]
        max_pts = float(item["max_points"])
        if resp is None:
            return 0.0
        if typ == "single_choice":
            correct = key.get("correct") or []
            return max_pts if resp in correct else 0.0
        if typ == "multi_select":
            got = set(resp if isinstance(resp, list) else [])
            want = set(key.get("correct") or [])
            return max_pts if got == want else 0.0
        if typ == "true_false":
            return max_pts if bool(resp) is bool(key.get("correct")) else 0.0
        if typ == "numeric":
            try:
                val = float(resp)
            except (TypeError, ValueError):
                return 0.0
            if not math.isfinite(val):
                return 0.0
            tolerance = float(key.get("tolerance") or 0)
            return max_pts if abs(val - float(key.get("correct", 0))) <= tolerance else 0.0
        if typ == "short_response":
            norm = str(resp).strip().lower()
            return max_pts if norm == str(key.get("correct_normalized", "")).lower() else 0.0
        return 0.0

    def _attempt_result(self, attempt_id: str) -> dict[str, Any]:
        a = self._attempt(attempt_id)
        manual = [
            r["item_id"]
            for r in self.conn.execute(
                """
                SELECT i.item_id FROM quiz_items i
                JOIN quiz_responses r ON r.item_id = i.item_id AND r.attempt_id=?
                WHERE i.grading_mode='manual' AND r.manual_graded=0
                """,
                (attempt_id,),
            ).fetchall()
        ]
        return {
            "attempt_id": attempt_id,
            "status": a["status"],
            "score": a["score"],
            "max_score": a["max_score"],
            "manual_items": manual,
            "server_timed_out": bool(a["server_timed_out"]),
            "deadline_at": a["deadline_at"],
            "answer_key_exposed": False,
            "idempotent_replay": True,
        }

    def grade_manual_quiz_item(
        self, actor: Actor, attempt_id: str, item_id: str, points: float, comment: str = ""
    ) -> dict[str, Any]:
        """Validate everything before mutating anything."""
        attempt = self._attempt(attempt_id)
        self.sections.require_staff_scope(actor, attempt["section_id"])

        item = self.conn.execute(
            "SELECT * FROM quiz_items WHERE item_id=? AND quiz_id=?",
            (item_id, attempt["quiz_id"]),
        ).fetchone()
        if not item:
            # Never let a nonexistent or foreign item silently promote an attempt to graded.
            raise ServiceError("ITEM_NOT_FOUND", 404)
        if item["grading_mode"] != "manual":
            raise ServiceError("ITEM_NOT_MANUAL_GRADED", 400)
        if attempt["status"] not in GRADABLE_ATTEMPT_STATES:
            raise ServiceError("ATTEMPT_NOT_GRADABLE", 400)

        try:
            pts = float(points)
        except (TypeError, ValueError) as e:
            raise ServiceError("INVALID_POINTS", 400) from e
        if not math.isfinite(pts):
            raise ServiceError("INVALID_POINTS", 400)
        if pts < 0 or pts > float(item["max_points"]):
            raise ServiceError("POINTS_OUT_OF_BOUNDS", 400)

        response = self.conn.execute(
            "SELECT * FROM quiz_responses WHERE attempt_id=? AND item_id=?",
            (attempt_id, item_id),
        ).fetchone()
        if not response:
            raise ServiceError("RESPONSE_NOT_FOUND", 404)

        quiz = self._quiz(attempt["quiz_id"])
        if quiz["section_id"] != attempt["section_id"] or quiz["site_id"] != attempt["site_id"]:
            raise ServiceError("ATTEMPT_SCOPE_INCONSISTENT", 409)
        learner = self.conn.execute(
            "SELECT site_id FROM users WHERE user_id=?", (attempt["learner_id"],)
        ).fetchone()
        if not learner or learner["site_id"] != attempt["site_id"]:
            raise ServiceError("ATTEMPT_SCOPE_INCONSISTENT", 409)

        before = {
            "points_earned": response["points_earned"],
            "manual_graded": response["manual_graded"],
            "attempt_status": attempt["status"],
            "attempt_score": attempt["score"],
        }

        txn.enter(self.conn, "manual_grade")
        try:
            now = _now()
            self.conn.execute(
                """
                UPDATE quiz_responses
                SET points_earned=?, manual_graded=1, graded_by=?, graded_at=?, manual_comment=?
                WHERE attempt_id=? AND item_id=?
                """,
                (pts, actor.actor_id, now, comment, attempt_id, item_id),
            )
            rows = self.conn.execute(
                "SELECT points_earned FROM quiz_responses WHERE attempt_id=?", (attempt_id,)
            ).fetchall()
            score = sum(float(r["points_earned"] or 0) for r in rows)
            remaining = self.conn.execute(
                """
                SELECT COUNT(*) AS c FROM quiz_items i
                LEFT JOIN quiz_responses r
                  ON r.item_id = i.item_id AND r.attempt_id = ?
                WHERE i.quiz_id = ? AND i.grading_mode='manual'
                  AND (r.response_id IS NULL OR r.manual_graded = 0)
                """,
                (attempt_id, attempt["quiz_id"]),
            ).fetchone()["c"]
            # Only fully graded once every required manual item has a grade.
            new_status = attempt["status"] if remaining else "graded"
            if attempt["status"] == "timed_out" and remaining:
                new_status = "timed_out"
            self.conn.execute(
                "UPDATE quiz_attempts SET score=?, status=? WHERE attempt_id=?",
                (score, new_status, attempt_id),
            )
            self._audit(
                actor,
                "quiz_manual_grade",
                "quiz_attempt",
                attempt_id,
                {
                    "item_id": item_id,
                    "comment": comment,
                    "before": before,
                    "after": {
                        "points_earned": pts,
                        "manual_graded": 1,
                        "attempt_status": new_status,
                        "attempt_score": score,
                    },
                    "manual_items_remaining": remaining,
                },
            )
            txn.release(self.conn, "manual_grade")
        except Exception:
            txn.rollback(self.conn, "manual_grade")
            raise
        txn.commit(self.conn)
        return {
            "attempt_id": attempt_id,
            "item_id": item_id,
            "points": pts,
            "score": score,
            "status": new_status,
            "manual_items_remaining": remaining,
        }

    def instructor_attempt_detail(self, actor: Actor, attempt_id: str) -> dict[str, Any]:
        attempt = self._attempt(attempt_id)
        self.sections.require_staff_scope(actor, attempt["section_id"])
        responses = self.conn.execute(
            """
            SELECT i.item_id, i.ordinal, i.item_type, i.prompt, i.max_points, i.grading_mode,
                   r.response_json, r.points_earned, r.auto_graded, r.manual_graded,
                   r.manual_comment
            FROM quiz_items i
            LEFT JOIN quiz_responses r ON r.item_id = i.item_id AND r.attempt_id = ?
            WHERE i.quiz_id = ?
            ORDER BY i.ordinal
            """,
            (attempt_id, attempt["quiz_id"]),
        ).fetchall()
        return {
            "attempt_id": attempt_id,
            "quiz_id": attempt["quiz_id"],
            "learner_id": attempt["learner_id"],
            "section_id": attempt["section_id"],
            "status": attempt["status"],
            "score": attempt["score"],
            "max_score": attempt["max_score"],
            "server_timed_out": bool(attempt["server_timed_out"]),
            "deadline_at": attempt["deadline_at"],
            "submitted_at": attempt["submitted_at"],
            "items": [
                {
                    "item_id": r["item_id"],
                    "ordinal": r["ordinal"],
                    "item_type": r["item_type"],
                    "prompt": r["prompt"],
                    "max_points": r["max_points"],
                    "grading_mode": r["grading_mode"],
                    "response": json.loads(r["response_json"]) if r["response_json"] else None,
                    "points_earned": r["points_earned"],
                    "auto_graded": bool(r["auto_graded"]),
                    "manual_graded": bool(r["manual_graded"]),
                    "manual_comment": r["manual_comment"],
                }
                for r in responses
            ],
        }

    def learner_attempt_detail(self, actor: Actor, attempt_id: str) -> dict[str, Any]:
        """A learner's own result view.

        Deliberately narrower than the instructor view: it omits the answer key,
        `auto_graded`, and every other item this learner has not been shown. Items
        the learner never answered are not listed at all, so an unanswered prompt
        cannot leak the shape of the key.
        """
        attempt = self._attempt(attempt_id)
        if attempt["learner_id"] != actor.actor_id:
            raise ServiceError("ATTEMPT_NOT_OWNED", 403)
        self.sections.require_learner_enrollment(actor, attempt["section_id"])
        responses = self.conn.execute(
            """
            SELECT i.item_id, i.ordinal, i.prompt, i.max_points, i.grading_mode,
                   r.response_json, r.points_earned, r.manual_graded, r.manual_comment
            FROM quiz_responses r
            JOIN quiz_items i ON i.item_id = r.item_id
            WHERE r.attempt_id = ?
            ORDER BY i.ordinal
            """,
            (attempt_id,),
        ).fetchall()
        return {
            "attempt_id": attempt_id,
            "quiz_id": attempt["quiz_id"],
            "learner_id": attempt["learner_id"],
            "status": attempt["status"],
            "score": attempt["score"],
            "max_score": attempt["max_score"],
            "started_at": attempt["started_at"],
            "deadline_at": attempt["deadline_at"],
            "submitted_at": attempt["submitted_at"],
            "responses": [
                {
                    "item_id": r["item_id"],
                    "prompt": r["prompt"],
                    "grading_mode": r["grading_mode"],
                    "response": json.loads(r["response_json"]) if r["response_json"] else "",
                    # Null while an instructor still has to score it by hand.
                    "points_awarded": r["points_earned"],
                    "max_points": r["max_points"],
                    "manual_graded": int(bool(r["manual_graded"])),
                    "manual_comment": r["manual_comment"],
                }
                for r in responses
            ],
        }

    def instructor_manual_queue(
        self, actor: Actor, section_id: str, anonymous: bool = False
    ) -> list[dict[str, Any]]:
        self.sections.require_staff_scope(actor, section_id)
        rows = self.conn.execute(
            """
            SELECT a.attempt_id, a.learner_id, a.quiz_id, a.status, a.submitted_at,
                   a.score, a.max_score,
                   (SELECT COUNT(*) FROM quiz_items i
                    LEFT JOIN quiz_responses r ON r.item_id=i.item_id AND r.attempt_id=a.attempt_id
                    WHERE i.quiz_id=a.quiz_id AND i.grading_mode='manual'
                      AND (r.response_id IS NULL OR r.manual_graded=0)) AS pending_manual
            FROM quiz_attempts a
            WHERE a.section_id=? AND a.status IN ('submitted','timed_out')
            ORDER BY a.submitted_at ASC
            """,
            (section_id,),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            if anonymous:
                item["learner_id"] = f"anon_{_sha256_text(r['learner_id'])[:8]}"
            out.append(item)
        return out

    # --- labs ----------------------------------------------------------------

    def get_lab(self, actor: Actor, lab_id: str) -> dict[str, Any]:
        lab = self._lab(lab_id)
        self.sections.require_section_access(actor, lab["section_id"])
        return {
            "lab_id": lab_id,
            "title": lab["title"],
            "mode": lab["mode"],
            "section_id": lab["section_id"],
            "runner_id": lab["runner_id"],
            "offline_eligible": bool(lab["offline_eligible"]),
            "spec": json.loads(lab["spec_json"]),
        }

    def complete_lab_run(
        self,
        actor: Actor,
        lab_id: str,
        *,
        evidence: dict[str, Any],
        artifact_hashes: list[str],
        client_mutation_id: str,
        fabricate_hardware: bool = False,
        learner_input: str | None = None,
    ) -> dict[str, Any]:
        lab = self._lab(lab_id)
        self.sections.require_learner_enrollment(actor, lab["section_id"])
        # Never fabricate hardware evidence — reject explicit fabricate attempts.
        if fabricate_hardware or evidence.get("hardware_fabricated"):
            raise ServiceError("HARDWARE_EVIDENCE_FABRICATION_FORBIDDEN", 400)
        if lab["mode"] == "DEVICE_HARDWARE_ASSISTED" and not evidence.get("device_attestation"):
            raise ServiceError("HARDWARE_EVIDENCE_REQUIRED", 400)

        existing = self.conn.execute(
            "SELECT * FROM lab_runs WHERE client_mutation_id=? AND learner_id=? AND lab_id=?",
            (client_mutation_id, actor.actor_id, lab_id),
        ).fetchone()
        if existing:
            return self._lab_run_dict(existing) | {"idempotent_replay": True}

        claimed = {
            "claimed_evidence": evidence,
            "claimed_artifact_hashes": list(artifact_hashes or []),
        }
        computed: dict[str, Any] = {}
        status = "completed"
        evidence_source = "learner_reported"
        authoritative_hashes = list(artifact_hashes or [])
        runner_id = None
        exit_code = None
        duration_ms = None
        truncated = 0

        if lab["mode"] == "LOCAL_SOFTWARE":
            try:
                spec = resolve_runner(lab["runner_id"])
                computed = run_local_software(
                    spec, learner_input if learner_input is not None else str(evidence.get("input_text") or "")
                )
            except LabRunnerError as e:
                raise ServiceError(e.code, 400) from e
            runner_id = computed["runner_id"]
            exit_code = computed["exit_code"]
            duration_ms = computed["duration_ms"]
            truncated = 1 if computed["truncated"] else 0
            evidence_source = "server_computed"
            if computed["timed_out"]:
                status = "timed_out"
            elif computed["exit_code"] != 0:
                status = "failed"
            # Client-claimed hashes are recorded but never authoritative.
            authoritative_hashes = [computed["stdout_sha256"], computed["input_sha256"]]
        elif lab["mode"] == "DEVICE_HARDWARE_ASSISTED":
            evidence_source = "external_attested"

        run_id = _id("labrun")
        self.conn.execute(
            """
            INSERT INTO lab_runs(
              run_id, lab_id, learner_id, section_id, site_id, status, evidence_json,
              computed_evidence_json, evidence_source, artifact_hashes_json, runner_id,
              runner_exit_code, runner_duration_ms, runner_truncated,
              hardware_evidence_fabricated, started_at, completed_at, client_mutation_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                lab_id,
                actor.actor_id,
                lab["section_id"],
                lab["site_id"],
                status,
                json.dumps(claimed),
                json.dumps(computed),
                evidence_source,
                json.dumps(authoritative_hashes),
                runner_id,
                exit_code,
                duration_ms,
                truncated,
                0,
                _now(),
                _now(),
                client_mutation_id,
            ),
        )
        txn.commit(self.conn)
        return self._lab_run_dict(
            self.conn.execute("SELECT * FROM lab_runs WHERE run_id=?", (run_id,)).fetchone()
        )

    def _lab_run_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "lab_id": row["lab_id"],
            "learner_id": row["learner_id"],
            "section_id": row["section_id"],
            "status": row["status"],
            "evidence_source": row["evidence_source"],
            "runner_id": row["runner_id"],
            "runner_exit_code": row["runner_exit_code"],
            "runner_duration_ms": row["runner_duration_ms"],
            "runner_truncated": bool(row["runner_truncated"]),
            "claimed": json.loads(row["evidence_json"] or "{}"),
            "computed_evidence": json.loads(row["computed_evidence_json"] or "{}"),
            "artifact_hashes": json.loads(row["artifact_hashes_json"] or "[]"),
            "hardware_evidence_fabricated": bool(row["hardware_evidence_fabricated"]),
            "completed_at": row["completed_at"],
        }

    def list_lab_runs(self, actor: Actor, lab_id: str) -> list[dict[str, Any]]:
        lab = self._lab(lab_id)
        if self.sections.has_staff_scope(actor, lab["section_id"]):
            rows = self.conn.execute(
                "SELECT * FROM lab_runs WHERE lab_id=? ORDER BY completed_at DESC", (lab_id,)
            ).fetchall()
        else:
            self.sections.require_learner_enrollment(actor, lab["section_id"])
            rows = self.conn.execute(
                "SELECT * FROM lab_runs WHERE lab_id=? AND learner_id=? ORDER BY completed_at DESC",
                (lab_id, actor.actor_id),
            ).fetchall()
        return [self._lab_run_dict(r) for r in rows]

    # --- discussions ---------------------------------------------------------

    def _thread(self, thread_id: str) -> sqlite3.Row:
        thr = self.conn.execute(
            "SELECT * FROM discussion_threads WHERE thread_id=?", (thread_id,)
        ).fetchone()
        if not thr:
            raise ServiceError("THREAD_NOT_FOUND", 404)
        return thr

    def create_thread(self, actor: Actor, section_id: str, title: str) -> dict[str, Any]:
        self.sections.require_section_access(actor, section_id)
        if not title.strip():
            raise ServiceError("TITLE_REQUIRED", 400)
        thread_id = _id("thr")
        self.conn.execute(
            """
            INSERT INTO discussion_threads(
              thread_id, section_id, site_id, title, created_by, created_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (thread_id, section_id, actor.site_id, title, actor.actor_id, _now()),
        )
        txn.commit(self.conn)
        return {"thread_id": thread_id, "title": title, "section_id": section_id}

    def list_threads(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        self.sections.require_section_access(actor, section_id)
        rows = self.conn.execute(
            "SELECT * FROM discussion_threads WHERE section_id=? ORDER BY created_at DESC",
            (section_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_posts(self, actor: Actor, thread_id: str) -> list[dict[str, Any]]:
        thr = self._thread(thread_id)
        self.sections.require_section_access(actor, thr["section_id"])
        staff = self.sections.has_staff_scope(actor, thr["section_id"])
        rows = self.conn.execute(
            "SELECT * FROM discussion_posts WHERE thread_id=? ORDER BY created_at", (thread_id,)
        ).fetchall()
        out = []
        for r in rows:
            post = dict(r)
            if post["deleted"] and not staff:
                post["body"] = "[removed by moderator]"
                post.pop("moderation_note", None)
            elif not staff:
                post.pop("moderation_note", None)
            out.append(post)
        return out

    def post_or_draft(
        self,
        actor: Actor,
        thread_id: str,
        body: str,
        *,
        parent_post_id: str | None = None,
        as_draft: bool = False,
        client_mutation_id: str | None = None,
    ) -> dict[str, Any]:
        thr = self._thread(thread_id)
        self.sections.require_section_access(actor, thr["section_id"])
        staff = self.sections.has_staff_scope(actor, thr["section_id"])
        if thr["locked"] and not staff:
            raise ServiceError("THREAD_LOCKED", 403)
        if parent_post_id:
            parent = self.conn.execute(
                "SELECT thread_id FROM discussion_posts WHERE post_id=?", (parent_post_id,)
            ).fetchone()
            if not parent or parent["thread_id"] != thread_id:
                raise ServiceError("PARENT_POST_NOT_IN_THREAD", 400)
        if as_draft:
            draft_key = f"discussion:{thread_id}:{actor.actor_id}:{client_mutation_id or _id('d')}"
            version_id = _id("dver")
            payload = {"body": body, "thread_id": thread_id, "parent_post_id": parent_post_id}
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            self.conn.execute(
                """
                INSERT INTO draft_versions(
                  version_id, draft_key, entity_type, entity_id, user_id, section_id,
                  revision, payload_json, payload_hash, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    version_id,
                    draft_key,
                    "discussion_draft",
                    thread_id,
                    actor.actor_id,
                    thr["section_id"],
                    1,
                    payload_json,
                    _sha256_text(payload_json),
                    _now(),
                ),
            )
            txn.commit(self.conn)
            return {"draft": True, "draft_key": draft_key, "version_id": version_id}

        post_id = _id("dpost")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO discussion_posts(
              post_id, thread_id, parent_post_id, author_id, body, revision, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (post_id, thread_id, parent_post_id, actor.actor_id, body, 1, now, now),
        )
        txn.commit(self.conn)
        return {"draft": False, "post_id": post_id, "revision": 1}

    def moderate_post(
        self, actor: Actor, post_id: str, note: str, delete: bool = False
    ) -> dict[str, Any]:
        post = self.conn.execute(
            """
            SELECT p.*, t.section_id FROM discussion_posts p
            JOIN discussion_threads t ON t.thread_id = p.thread_id
            WHERE p.post_id=?
            """,
            (post_id,),
        ).fetchone()
        if not post:
            raise ServiceError("POST_NOT_FOUND", 404)
        self.sections.require_staff_scope(actor, post["section_id"])
        before = {"deleted": post["deleted"], "moderation_note": post["moderation_note"]}
        self.conn.execute(
            """
            UPDATE discussion_posts
            SET moderation_note=?, deleted=?, moderated_by=?, updated_at=?
            WHERE post_id=?
            """,
            (note, 1 if delete else 0, actor.actor_id, _now(), post_id),
        )
        self._audit(
            actor,
            "discussion_moderate",
            "discussion_post",
            post_id,
            {"before": before, "after": {"deleted": bool(delete), "moderation_note": note}},
        )
        txn.commit(self.conn)
        return {"post_id": post_id, "moderated": True, "deleted": delete}

    # --- groups --------------------------------------------------------------

    def create_group(
        self, actor: Actor, section_id: str, name: str, member_ids: list[str]
    ) -> dict[str, Any]:
        self.sections.require_staff_scope(actor, section_id)
        for mid in member_ids:
            if not self.sections.is_enrolled(mid, section_id):
                raise ServiceError("MEMBER_NOT_ENROLLED", 400)
        group_id = _id("grp")
        now = _now()
        try:
            self.conn.execute(
                """
                INSERT INTO groups(group_id, section_id, site_id, name, created_by, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (group_id, section_id, actor.site_id, name, actor.actor_id, now),
            )
        except sqlite3.IntegrityError as e:
            raise ServiceError("GROUP_NAME_TAKEN", 409) from e
        for mid in member_ids:
            self.conn.execute(
                "INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?,?,?,?)",
                (group_id, mid, "member", now),
            )
        txn.commit(self.conn)
        return {"group_id": group_id, "name": name, "section_id": section_id, "members": member_ids}

    def _group(self, group_id: str) -> sqlite3.Row:
        g = self.conn.execute("SELECT * FROM groups WHERE group_id=?", (group_id,)).fetchone()
        if not g:
            raise ServiceError("GROUP_NOT_FOUND", 404)
        return g

    def assert_group_member(self, actor: Actor, group_id: str) -> sqlite3.Row:
        g = self._group(group_id)
        if g["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        if self.sections.has_staff_scope(actor, g["section_id"]):
            return g
        mem = self.conn.execute(
            "SELECT * FROM group_members WHERE group_id=? AND user_id=?",
            (group_id, actor.actor_id),
        ).fetchone()
        if not mem:
            raise ServiceError("NOT_GROUP_MEMBER", 403)
        self.sections.require_learner_enrollment(actor, g["section_id"])
        return g

    def group_submit(
        self,
        actor: Actor,
        group_id: str,
        activity_id: str,
        activity_type: str,
        payload: dict[str, Any],
        contributions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.assert_group_member(actor, group_id)
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        gs_id = _id("gsub")
        self.conn.execute(
            """
            INSERT INTO group_submissions(
              group_submission_id, group_id, activity_id, activity_type, payload_json,
              content_hash, submitted_by, contributions_json, submitted_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                gs_id,
                group_id,
                activity_id,
                activity_type,
                content,
                _sha256_text(content),
                actor.actor_id,
                json.dumps(contributions),
                _now(),
            ),
        )
        txn.commit(self.conn)
        return {"group_submission_id": gs_id, "content_hash": _sha256_text(content)}

    def list_group_submissions(self, actor: Actor, group_id: str) -> list[dict[str, Any]]:
        self.assert_group_member(actor, group_id)
        rows = self.conn.execute(
            "SELECT * FROM group_submissions WHERE group_id=?", (group_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_groups(self, actor: Actor, section_id: str) -> list[dict[str, Any]]:
        self.sections.require_section_access(actor, section_id)
        staff = self.sections.has_staff_scope(actor, section_id)
        rows = self.conn.execute(
            "SELECT * FROM groups WHERE section_id=? ORDER BY name", (section_id,)
        ).fetchall()
        out = []
        for g in rows:
            members = [
                r["user_id"]
                for r in self.conn.execute(
                    "SELECT user_id FROM group_members WHERE group_id=?", (g["group_id"],)
                ).fetchall()
            ]
            if not staff and actor.actor_id not in members:
                continue
            out.append({**dict(g), "members": members})
        return out

    # --- grading efficiency --------------------------------------------------

    def next_ungraded(self, actor: Actor, section_id: str, anonymous: bool = False) -> dict[str, Any]:
        self.sections.require_staff_scope(actor, section_id)
        row = self.conn.execute(
            """
            SELECT a.attempt_id, a.learner_id, a.quiz_id, a.status
            FROM quiz_attempts a
            WHERE a.section_id=? AND a.status='submitted'
            ORDER BY a.submitted_at ASC
            LIMIT 1
            """,
            (section_id,),
        ).fetchone()
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND status='submitted'",
            (section_id,),
        ).fetchone()["c"]
        if not row:
            return {"next": None, "ungraded_count": count}
        nxt = dict(row)
        if anonymous:
            nxt["learner_id"] = f"anon_{_sha256_text(row['learner_id'])[:8]}"
        return {"next": nxt, "ungraded_count": count}

    def add_reusable_comment(
        self, actor: Actor, body: str, section_id: str | None = None, criterion_id: str | None = None
    ) -> dict[str, Any]:
        if section_id:
            self.sections.require_staff_scope(actor, section_id)
        elif not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        cid = _id("rcom")
        self.conn.execute(
            """
            INSERT INTO reusable_comments(
              comment_id, site_id, section_id, author_id, body, criterion_id, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (cid, actor.site_id, section_id, actor.actor_id, body, criterion_id, _now()),
        )
        txn.commit(self.conn)
        return {"comment_id": cid, "body": body}

    def batch_apply_criterion(
        self,
        actor: Actor,
        section_id: str,
        criterion_id: str,
        points: float,
        attempt_ids: list[str],
        comment: str = "",
    ) -> dict[str, Any]:
        self.sections.require_staff_scope(actor, section_id)
        applied = 0
        skipped: list[dict[str, str]] = []
        for aid in attempt_ids:
            attempt = self.conn.execute(
                "SELECT section_id FROM quiz_attempts WHERE attempt_id=?", (aid,)
            ).fetchone()
            if not attempt or attempt["section_id"] != section_id:
                skipped.append({"attempt_id": aid, "reason": "ATTEMPT_NOT_IN_SECTION"})
                continue
            try:
                self.grade_manual_quiz_item(actor, aid, criterion_id, points, comment)
                applied += 1
            except ServiceError as e:
                skipped.append({"attempt_id": aid, "reason": e.code})
        batch_id = _id("gbatch")
        self.conn.execute(
            """
            INSERT INTO grading_batches(
              batch_id, instructor_id, section_id, criterion_id, points, comment,
              applied_count, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (batch_id, actor.actor_id, section_id, criterion_id, points, comment, applied, _now()),
        )
        txn.commit(self.conn)
        return {"batch_id": batch_id, "applied_count": applied, "skipped": skipped}

    def _resolve_regrade_scope(self, submission_id: str) -> tuple[str | None, str | None, str | None]:
        """Regrade targets are assignment submissions or quiz attempts; both carry a section."""
        sub = self.conn.execute(
            "SELECT learner_id, section_id FROM submissions WHERE submission_id=?",
            (submission_id,),
        ).fetchone()
        if sub:
            return sub["section_id"], sub["learner_id"], "submission"
        attempt = self.conn.execute(
            "SELECT learner_id, section_id FROM quiz_attempts WHERE attempt_id=?",
            (submission_id,),
        ).fetchone()
        if attempt:
            return attempt["section_id"], attempt["learner_id"], "quiz_attempt"
        return None, None, None

    def enqueue_regrade(self, actor: Actor, submission_id: str, reason: str) -> dict[str, Any]:
        section_id, owner_id, kind = self._resolve_regrade_scope(submission_id)
        if not section_id:
            raise ServiceError("REGRADE_TARGET_NOT_FOUND", 404)
        if actor.actor_id == owner_id:
            self.sections.require_learner_enrollment(actor, section_id)
        else:
            self.sections.require_staff_scope(actor, section_id)
        sec = self.conn.execute(
            "SELECT site_id FROM sections WHERE section_id=?", (section_id,)
        ).fetchone()
        rid = _id("regrade")
        self.conn.execute(
            """
            INSERT INTO regrade_queue(
              regrade_id, submission_id, section_id, site_id, requested_by, reason, status, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                submission_id,
                section_id,
                sec["site_id"] if sec else None,
                actor.actor_id,
                reason,
                "queued",
                _now(),
            ),
        )
        txn.commit(self.conn)
        return {"regrade_id": rid, "status": "queued", "section_id": section_id, "target": kind}

    def grading_progress(self, actor: Actor, section_id: str) -> dict[str, Any]:
        self.sections.require_staff_scope(actor, section_id)
        total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND submitted_at IS NOT NULL",
            (section_id,),
        ).fetchone()["c"]
        graded = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND status='graded'",
            (section_id,),
        ).fetchone()["c"]
        timed_out = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND status='timed_out'",
            (section_id,),
        ).fetchone()["c"]
        queued = self.conn.execute(
            "SELECT COUNT(*) AS c FROM regrade_queue WHERE section_id=? AND status='queued'",
            (section_id,),
        ).fetchone()["c"]
        return {
            "total_submitted": total,
            "graded": graded,
            "timed_out": timed_out,
            "regrade_queued": queued,
        }

    # --- section activity index ----------------------------------------------

    def section_activities(self, actor: Actor, section_id: str) -> dict[str, Any]:
        """Single index the client uses to render real activities (no debug JSON screens)."""
        self.sections.require_section_access(actor, section_id)
        staff = self.sections.has_staff_scope(actor, section_id)
        quizzes = self.conn.execute(
            "SELECT quiz_id, title, offline_eligible, high_integrity_timed, policies_json "
            "FROM quiz_definitions WHERE section_id=? ORDER BY title",
            (section_id,),
        ).fetchall()
        labs = self.conn.execute(
            "SELECT lab_id, title, mode, offline_eligible FROM lab_definitions "
            "WHERE section_id=? ORDER BY title",
            (section_id,),
        ).fetchall()
        threads = self.conn.execute(
            "SELECT thread_id, title, locked FROM discussion_threads WHERE section_id=? "
            "ORDER BY created_at DESC",
            (section_id,),
        ).fetchall()

        quiz_views = []
        for q in quizzes:
            policies = json.loads(q["policies_json"])
            entry = {
                "quiz_id": q["quiz_id"],
                "title": q["title"],
                "offline_eligible": bool(q["offline_eligible"]),
                "high_integrity_timed": bool(q["high_integrity_timed"]),
                "time_limit_minutes": policies.get("time_limit_minutes"),
                "attempt_limit": policies.get("attempt_limit"),
            }
            if not staff:
                attempts = self.conn.execute(
                    "SELECT attempt_id, attempt_number, status, score, max_score, deadline_at "
                    "FROM quiz_attempts WHERE quiz_id=? AND learner_id=? ORDER BY attempt_number",
                    (q["quiz_id"], actor.actor_id),
                ).fetchall()
                entry["my_attempts"] = [dict(a) for a in attempts]
            else:
                entry["pending_manual"] = self.conn.execute(
                    "SELECT COUNT(*) AS c FROM quiz_attempts WHERE quiz_id=? AND status='submitted'",
                    (q["quiz_id"],),
                ).fetchone()["c"]
            quiz_views.append(entry)

        accommodation = None
        if actor.is_learner and not staff:
            row = self.conn.execute(
                "SELECT time_multiplier, attempt_override, due_extension_minutes, "
                "alternate_modality FROM accommodations "
                "WHERE learner_id=? AND section_id=? AND active=1",
                (actor.actor_id, section_id),
            ).fetchone()
            accommodation = dict(row) if row else None

        return {
            "section_id": section_id,
            "staff_view": staff,
            "quizzes": quiz_views,
            "labs": [dict(r) for r in labs],
            "threads": [dict(r) for r in threads],
            "groups": self.list_groups(actor, section_id),
            "accommodation": accommodation,
        }

    # --- sync mutation bridge ------------------------------------------------

    def handle_sync_mutation(
        self,
        actor: Actor,
        *,
        entity_type: str,
        entity_id: str,
        base_revision: int,
        operation: str,
        payload: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any]:
        if entity_type == "quiz_attempt":
            if operation != "submit":
                raise ServiceError("UNSUPPORTED_OPERATION", 400)
            attempt_id = payload.get("attempt_id")
            if not attempt_id:
                raise ServiceError("ATTEMPT_ID_REQUIRED", 400)
            attempt = self._attempt(str(attempt_id))
            if attempt["section_id"] != section_id:
                raise ServiceError("ATTEMPT_SECTION_MISMATCH", 403)
            result = self.submit_quiz_attempt(
                actor,
                str(attempt_id),
                payload.get("responses") or {},
                client_mutation_id=payload.get("client_mutation_id") or entity_id,
                client_elapsed_minutes=payload.get("client_elapsed_minutes"),
            )
            return {"sync_status": "acknowledged", "revision": 1, **result}
        if entity_type == "discussion_draft":
            thread_id = payload.get("thread_id")
            if not thread_id:
                raise ServiceError("THREAD_ID_REQUIRED", 400)
            thr = self._thread(str(thread_id))
            if thr["section_id"] != section_id:
                raise ServiceError("THREAD_SECTION_MISMATCH", 403)
            result = self.post_or_draft(
                actor,
                str(thread_id),
                payload.get("body") or "",
                parent_post_id=payload.get("parent_post_id"),
                as_draft=operation == "draft",
                client_mutation_id=entity_id,
            )
            return {"sync_status": "acknowledged", "revision": 1, **result}
        if entity_type == "lab_run":
            lab_id = payload.get("lab_id") or entity_id
            lab = self._lab(str(lab_id))
            if lab["section_id"] != section_id:
                raise ServiceError("LAB_SECTION_MISMATCH", 403)
            result = self.complete_lab_run(
                actor,
                str(lab_id),
                evidence=payload.get("evidence") or {},
                artifact_hashes=payload.get("artifact_hashes") or [],
                client_mutation_id=payload.get("client_mutation_id") or entity_id,
                fabricate_hardware=bool(payload.get("fabricate_hardware")),
                learner_input=payload.get("learner_input"),
            )
            return {"sync_status": "acknowledged", "revision": 1, **result}
        raise ServiceError("UNKNOWN_ENTITY_TYPE", 400)


def _redact_accommodation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    redacted = dict(row)
    notes = redacted.pop("notes_private", None)
    redacted["notes_private_present"] = bool(notes)
    return redacted
