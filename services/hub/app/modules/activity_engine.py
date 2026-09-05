"""Gate A activity engine: quizzes, labs, discussions, groups, accommodations, grading efficiency."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError

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


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ActivityEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- seed helpers for tests ----------------------------------------------

    def seed_section_activities(self, *, section_id: str, site_id: str, instructor_id: str) -> dict[str, Any]:
        quiz_id = "quiz_dc_w01_gate_a"
        existing = self.conn.execute(
            "SELECT quiz_id FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
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
            "qi_sc": {"correct": ["b"]},
            "qi_ms": {"correct": ["a", "c"]},
            "qi_tf": {"correct": True},
            "qi_num": {"correct": 42, "tolerance": 0},
            "qi_short": {"correct_normalized": "digital confidence"},
        }
        self.conn.execute(
            """
            INSERT INTO quiz_definitions(
              quiz_id, section_id, site_id, title, policies_json, answer_key_json,
              offline_eligible, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                quiz_id,
                section_id,
                site_id,
                "Gate A Digital Confidence Quiz",
                json.dumps(policies),
                json.dumps(answer_key),
                1,
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
                (item_id, quiz_id, ord_, typ, prompt, json.dumps(opts), pts, mode),
            )

        lab_id = "lab_dc_local_software"
        self.conn.execute(
            """
            INSERT INTO lab_definitions(
              lab_id, section_id, site_id, title, mode, spec_json, offline_eligible, created_by, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
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
                        "environment": {"sandbox": True, "workdir": "/tmp/waike-lab", "time_limit_s": 30},
                        "steps": ["hash fixture", "record digest"],
                        "expected_evidence": ["stdout_hash"],
                        "grading_mode": "manual",
                        "offline_eligible": True,
                        "safety_notes": ["no network", "no production secrets"],
                    }
                ),
                1,
                instructor_id,
                _now(),
            ),
        )
        self.conn.commit()
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
        if not actor.is_instructor_side:
            raise ServiceError("STAFF_ONLY", 403)
        sec = self.conn.execute(
            "SELECT site_id FROM sections WHERE section_id=?", (section_id,)
        ).fetchone()
        if not sec or sec["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        existing = self.conn.execute(
            "SELECT * FROM accommodations WHERE learner_id=? AND section_id=?",
            (learner_id, section_id),
        ).fetchone()
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
        self.conn.execute(
            """
            INSERT INTO audit_events(event_id, actor_id, action, entity_type, entity_id, detail_json, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                _id("aud"),
                actor.actor_id,
                "accommodation_upsert",
                "accommodation",
                acc_id,
                json.dumps({"learner_id": learner_id, "section_id": section_id}),
                now,
            ),
        )
        self.conn.commit()
        return self.get_accommodation(actor, learner_id, section_id)

    def get_accommodation(self, actor: Actor, learner_id: str, section_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM accommodations WHERE learner_id=? AND section_id=? AND active=1",
            (learner_id, section_id),
        ).fetchone()
        if not row:
            raise ServiceError("ACCOMMODATION_NOT_FOUND", 404)
        # Peers must never see private accommodation details.
        if actor.actor_id != learner_id and not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        data = dict(row)
        if actor.actor_id == learner_id and not actor.is_instructor_side:
            # Learner sees applied effects, not private staff notes.
            data.pop("notes_private", None)
        return data

    def peer_cannot_read_accommodation(self, peer: Actor, learner_id: str, section_id: str) -> bool:
        try:
            self.get_accommodation(peer, learner_id, section_id)
            return False
        except ServiceError as e:
            return e.code == "FORBIDDEN"

    def _effective_policies(self, quiz_id: str, learner_id: str, section_id: str) -> dict[str, Any]:
        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        if not quiz:
            raise ServiceError("QUIZ_NOT_FOUND", 404)
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
                policies["availability_end"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
            policies["accommodation_applied"] = True
            policies["alternate_modality"] = acc["alternate_modality"]
        else:
            policies["accommodation_applied"] = False
        return policies

    # --- quizzes -------------------------------------------------------------

    def learner_quiz_view(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        if not quiz:
            raise ServiceError("QUIZ_NOT_FOUND", 404)
        if quiz["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        items = self.conn.execute(
            "SELECT item_id, ordinal, item_type, prompt, options_json, max_points, grading_mode "
            "FROM quiz_items WHERE quiz_id=? ORDER BY ordinal",
            (quiz_id,),
        ).fetchall()
        # Answer keys NEVER returned to learners.
        view = {
            "quiz_id": quiz_id,
            "title": quiz["title"],
            "section_id": quiz["section_id"],
            "offline_eligible": bool(quiz["offline_eligible"]),
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
        if "answer_key" in view or "answer_key_json" in view:
            raise ServiceError("ANSWER_KEY_LEAK", 500)
        return view

    def instructor_answer_key(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        if not quiz:
            raise ServiceError("QUIZ_NOT_FOUND", 404)
        if quiz["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        return {"quiz_id": quiz_id, "answer_key": json.loads(quiz["answer_key_json"])}

    def start_quiz_attempt(self, actor: Actor, quiz_id: str) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_REQUIRED", 403)
        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (quiz_id,)
        ).fetchone()
        if not quiz:
            raise ServiceError("QUIZ_NOT_FOUND", 404)
        policies = self._effective_policies(quiz_id, actor.actor_id, quiz["section_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE quiz_id=? AND learner_id=?",
            (quiz_id, actor.actor_id),
        ).fetchone()["c"]
        limit = int(policies.get("attempt_limit") or 1)
        if count >= limit:
            raise ServiceError("ATTEMPT_LIMIT", 403)
        # Availability window (server authoritative)
        now = datetime.now(tz=timezone.utc)
        if policies.get("availability_start") and now < _parse(policies["availability_start"]):
            raise ServiceError("NOT_AVAILABLE", 403)
        if policies.get("availability_end") and now > _parse(policies["availability_end"]):
            raise ServiceError("NOT_AVAILABLE", 403)
        attempt_id = _id("qatt")
        self.conn.execute(
            """
            INSERT INTO quiz_attempts(
              attempt_id, quiz_id, learner_id, section_id, attempt_number,
              started_at, status, accommodation_json
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                attempt_id,
                quiz_id,
                actor.actor_id,
                quiz["section_id"],
                count + 1,
                _now(),
                "in_progress",
                json.dumps({"applied": policies.get("accommodation_applied", False)}),
            ),
        )
        self.conn.commit()
        return {
            "attempt_id": attempt_id,
            "attempt_number": count + 1,
            "started_at": _now(),
            "time_limit_minutes": policies.get("time_limit_minutes"),
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
        if not actor.is_learner:
            raise ServiceError("LEARNER_REQUIRED", 403)
        # Idempotency on client_mutation_id
        if client_mutation_id:
            existing = self.conn.execute(
                "SELECT * FROM quiz_attempts WHERE client_mutation_id=?",
                (client_mutation_id,),
            ).fetchone()
            if existing and existing["status"] in {"submitted", "graded", "returned"}:
                return self._attempt_result(existing["attempt_id"])

        attempt = self.conn.execute(
            "SELECT * FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if not attempt or attempt["learner_id"] != actor.actor_id:
            raise ServiceError("ATTEMPT_NOT_FOUND", 404)
        if attempt["status"] != "in_progress":
            raise ServiceError("ATTEMPT_NOT_OPEN", 400)

        policies = self._effective_policies(
            attempt["quiz_id"], actor.actor_id, attempt["section_id"]
        )
        started = _parse(attempt["started_at"])
        limit_m = policies.get("time_limit_minutes")
        timed_out = False
        if limit_m is not None:
            # Server clock authoritative — ignore sole client claim.
            if datetime.now(tz=timezone.utc) > started + timedelta(minutes=float(limit_m) + 0.5):
                timed_out = True
            if client_elapsed_minutes is not None and client_elapsed_minutes > float(limit_m) * 2:
                # Absurd client clock rejected; still use server.
                timed_out = timed_out or False

        quiz = self.conn.execute(
            "SELECT * FROM quiz_definitions WHERE quiz_id=?", (attempt["quiz_id"],)
        ).fetchone()
        answer_key = json.loads(quiz["answer_key_json"])
        items = self.conn.execute(
            "SELECT * FROM quiz_items WHERE quiz_id=?", (attempt["quiz_id"],)
        ).fetchall()

        score = 0.0
        max_score = 0.0
        manual_items: list[str] = []
        for item in items:
            max_score += float(item["max_points"])
            resp = responses.get(item["item_id"])
            self.conn.execute(
                """
                INSERT OR REPLACE INTO quiz_responses(
                  response_id, attempt_id, item_id, response_json, points_earned, auto_graded
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    _id("qresp"),
                    attempt_id,
                    item["item_id"],
                    json.dumps(resp),
                    None,
                    0,
                ),
            )
            if item["grading_mode"] == "manual":
                manual_items.append(item["item_id"])
                continue
            pts = self._grade_objective(item, resp, answer_key.get(item["item_id"], {}))
            score += pts
            self.conn.execute(
                "UPDATE quiz_responses SET points_earned=?, auto_graded=1 WHERE attempt_id=? AND item_id=?",
                (pts, attempt_id, item["item_id"]),
            )

        status = "graded" if not manual_items else "submitted"
        # Learners cannot submit authoritative grade — only server computes.
        self.conn.execute(
            """
            UPDATE quiz_attempts SET
              submitted_at=?, status=?, score=?, max_score=?, server_timed_out=?,
              client_mutation_id=COALESCE(?, client_mutation_id)
            WHERE attempt_id=?
            """,
            (
                _now(),
                status,
                score,
                max_score,
                1 if timed_out else 0,
                client_mutation_id,
                attempt_id,
            ),
        )
        self.conn.commit()
        return {
            "attempt_id": attempt_id,
            "status": status,
            "score": score,
            "max_score": max_score,
            "manual_items": manual_items,
            "server_timed_out": timed_out,
            "answer_key_exposed": False,
        }

    def _grade_objective(self, item: sqlite3.Row, resp: Any, key: dict[str, Any]) -> float:
        typ = item["item_type"]
        max_pts = float(item["max_points"])
        if resp is None:
            return 0.0
        if typ == "single_choice":
            return max_pts if resp in key.get("correct", []) or resp == key.get("correct", [None])[0] else 0.0
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
            return max_pts if abs(val - float(key.get("correct", 0))) <= float(key.get("tolerance") or 0) else 0.0
        if typ == "short_response":
            norm = str(resp).strip().lower()
            return max_pts if norm == str(key.get("correct_normalized", "")).lower() else 0.0
        return 0.0

    def _attempt_result(self, attempt_id: str) -> dict[str, Any]:
        a = self.conn.execute(
            "SELECT * FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        return {
            "attempt_id": attempt_id,
            "status": a["status"],
            "score": a["score"],
            "max_score": a["max_score"],
            "manual_items": [],
            "server_timed_out": bool(a["server_timed_out"]),
            "answer_key_exposed": False,
            "idempotent_replay": True,
        }

    def grade_manual_quiz_item(
        self, actor: Actor, attempt_id: str, item_id: str, points: float, comment: str = ""
    ) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        attempt = self.conn.execute(
            "SELECT * FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if not attempt:
            raise ServiceError("ATTEMPT_NOT_FOUND", 404)
        self.conn.execute(
            "UPDATE quiz_responses SET points_earned=? WHERE attempt_id=? AND item_id=?",
            (points, attempt_id, item_id),
        )
        rows = self.conn.execute(
            "SELECT points_earned FROM quiz_responses WHERE attempt_id=?", (attempt_id,)
        ).fetchall()
        score = sum(float(r["points_earned"] or 0) for r in rows)
        self.conn.execute(
            "UPDATE quiz_attempts SET score=?, status='graded' WHERE attempt_id=?",
            (score, attempt_id),
        )
        self.conn.execute(
            """
            INSERT INTO audit_events(event_id, actor_id, action, entity_type, entity_id, detail_json, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                _id("aud"),
                actor.actor_id,
                "quiz_manual_grade",
                "quiz_attempt",
                attempt_id,
                json.dumps({"item_id": item_id, "points": points, "comment": comment}),
                _now(),
            ),
        )
        self.conn.commit()
        return {"attempt_id": attempt_id, "score": score, "status": "graded"}

    # --- labs ----------------------------------------------------------------

    def get_lab(self, actor: Actor, lab_id: str) -> dict[str, Any]:
        lab = self.conn.execute(
            "SELECT * FROM lab_definitions WHERE lab_id=?", (lab_id,)
        ).fetchone()
        if not lab:
            raise ServiceError("LAB_NOT_FOUND", 404)
        if lab["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        spec = json.loads(lab["spec_json"])
        return {
            "lab_id": lab_id,
            "title": lab["title"],
            "mode": lab["mode"],
            "section_id": lab["section_id"],
            "offline_eligible": bool(lab["offline_eligible"]),
            "spec": spec,
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
    ) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_REQUIRED", 403)
        lab = self.conn.execute(
            "SELECT * FROM lab_definitions WHERE lab_id=?", (lab_id,)
        ).fetchone()
        if not lab:
            raise ServiceError("LAB_NOT_FOUND", 404)
        # Never fabricate hardware evidence — reject explicit fabricate attempts.
        if fabricate_hardware or evidence.get("hardware_fabricated"):
            raise ServiceError("HARDWARE_EVIDENCE_FABRICATION_FORBIDDEN", 400)
        if lab["mode"] == "DEVICE_HARDWARE_ASSISTED" and not evidence.get("device_attestation"):
            raise ServiceError("HARDWARE_EVIDENCE_REQUIRED", 400)

        existing = self.conn.execute(
            "SELECT * FROM lab_runs WHERE client_mutation_id=?", (client_mutation_id,)
        ).fetchone()
        if existing:
            return dict(existing) | {"idempotent_replay": True}

        run_id = _id("labrun")
        self.conn.execute(
            """
            INSERT INTO lab_runs(
              run_id, lab_id, learner_id, section_id, status, evidence_json,
              artifact_hashes_json, hardware_evidence_fabricated, started_at, completed_at,
              client_mutation_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                lab_id,
                actor.actor_id,
                lab["section_id"],
                "completed",
                json.dumps(evidence),
                json.dumps(artifact_hashes),
                0,
                _now(),
                _now(),
                client_mutation_id,
            ),
        )
        self.conn.commit()
        return {
            "run_id": run_id,
            "lab_id": lab_id,
            "status": "completed",
            "mode": lab["mode"],
            "artifact_hashes": artifact_hashes,
            "hardware_evidence_fabricated": False,
        }

    # --- discussions ---------------------------------------------------------

    def create_thread(self, actor: Actor, section_id: str, title: str) -> dict[str, Any]:
        sec = self.conn.execute(
            "SELECT site_id FROM sections WHERE section_id=?", (section_id,)
        ).fetchone()
        if not sec or sec["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        thread_id = _id("thr")
        self.conn.execute(
            """
            INSERT INTO discussion_threads(
              thread_id, section_id, site_id, title, created_by, created_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (thread_id, section_id, actor.site_id, title, actor.actor_id, _now()),
        )
        self.conn.commit()
        return {"thread_id": thread_id, "title": title, "section_id": section_id}

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
        thr = self.conn.execute(
            "SELECT * FROM discussion_threads WHERE thread_id=?", (thread_id,)
        ).fetchone()
        if not thr:
            raise ServiceError("THREAD_NOT_FOUND", 404)
        if thr["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        if thr["locked"] and not actor.is_instructor_side:
            raise ServiceError("THREAD_LOCKED", 403)
        if as_draft:
            # Offline draft stored as draft_versions for sync.
            draft_key = f"discussion:{thread_id}:{actor.actor_id}:{client_mutation_id or _id('d')}"
            version_id = _id("dver")
            payload = {"body": body, "thread_id": thread_id, "parent_post_id": parent_post_id}
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
                    json.dumps(payload),
                    _sha256_text(json.dumps(payload, sort_keys=True)),
                    _now(),
                ),
            )
            self.conn.commit()
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
        self.conn.commit()
        return {"draft": False, "post_id": post_id, "revision": 1}

    def moderate_post(self, actor: Actor, post_id: str, note: str, delete: bool = False) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        self.conn.execute(
            "UPDATE discussion_posts SET moderation_note=?, deleted=?, updated_at=? WHERE post_id=?",
            (note, 1 if delete else 0, _now(), post_id),
        )
        self.conn.commit()
        return {"post_id": post_id, "moderated": True, "deleted": delete}

    # --- groups --------------------------------------------------------------

    def create_group(self, actor: Actor, section_id: str, name: str, member_ids: list[str]) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        sec = self.conn.execute(
            "SELECT site_id FROM sections WHERE section_id=?", (section_id,)
        ).fetchone()
        if not sec or sec["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        group_id = _id("grp")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO groups(group_id, section_id, site_id, name, created_by, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (group_id, section_id, actor.site_id, name, actor.actor_id, now),
        )
        for mid in member_ids:
            self.conn.execute(
                "INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?,?,?,?)",
                (group_id, mid, "member", now),
            )
        self.conn.commit()
        return {"group_id": group_id, "name": name, "members": member_ids}

    def assert_group_member(self, actor: Actor, group_id: str) -> sqlite3.Row:
        g = self.conn.execute("SELECT * FROM groups WHERE group_id=?", (group_id,)).fetchone()
        if not g:
            raise ServiceError("GROUP_NOT_FOUND", 404)
        if g["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        mem = self.conn.execute(
            "SELECT * FROM group_members WHERE group_id=? AND user_id=?",
            (group_id, actor.actor_id),
        ).fetchone()
        if not mem and not actor.is_instructor_side:
            raise ServiceError("NOT_GROUP_MEMBER", 403)
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
        content = json.dumps(payload, sort_keys=True)
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
        self.conn.commit()
        return {"group_submission_id": gs_id, "content_hash": _sha256_text(content)}

    def list_group_submissions(self, actor: Actor, group_id: str) -> list[dict[str, Any]]:
        self.assert_group_member(actor, group_id)
        rows = self.conn.execute(
            "SELECT * FROM group_submissions WHERE group_id=?", (group_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- grading efficiency --------------------------------------------------

    def next_ungraded(self, actor: Actor, section_id: str, anonymous: bool = False) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        # Prefer quiz manual items, then assessment queue style submissions.
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
        if not actor.is_instructor_side:
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
        self.conn.commit()
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
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        applied = 0
        for aid in attempt_ids:
            try:
                self.grade_manual_quiz_item(actor, aid, criterion_id, points, comment)
                applied += 1
            except ServiceError:
                continue
        batch_id = _id("gbatch")
        self.conn.execute(
            """
            INSERT INTO grading_batches(
              batch_id, instructor_id, section_id, criterion_id, points, comment, applied_count, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (batch_id, actor.actor_id, section_id, criterion_id, points, comment, applied, _now()),
        )
        self.conn.commit()
        return {"batch_id": batch_id, "applied_count": applied}

    def enqueue_regrade(self, actor: Actor, submission_id: str, reason: str) -> dict[str, Any]:
        rid = _id("regrade")
        self.conn.execute(
            """
            INSERT INTO regrade_queue(regrade_id, submission_id, requested_by, reason, status, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (rid, submission_id, actor.actor_id, reason, "queued", _now()),
        )
        self.conn.commit()
        return {"regrade_id": rid, "status": "queued"}

    def grading_progress(self, actor: Actor, section_id: str) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("FORBIDDEN", 403)
        total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND submitted_at IS NOT NULL",
            (section_id,),
        ).fetchone()["c"]
        graded = self.conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE section_id=? AND status='graded'",
            (section_id,),
        ).fetchone()["c"]
        queued = self.conn.execute(
            "SELECT COUNT(*) AS c FROM regrade_queue WHERE status='queued'"
        ).fetchone()["c"]
        return {"total_submitted": total, "graded": graded, "regrade_queued": queued}

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
            if operation == "submit":
                result = self.submit_quiz_attempt(
                    actor,
                    payload["attempt_id"],
                    payload.get("responses") or {},
                    client_mutation_id=payload.get("client_mutation_id") or entity_id,
                    client_elapsed_minutes=payload.get("client_elapsed_minutes"),
                )
                return {"sync_status": "acknowledged", "revision": 1, **result}
            raise ServiceError("UNSUPPORTED_OPERATION", 400)
        if entity_type == "discussion_draft":
            result = self.post_or_draft(
                actor,
                payload["thread_id"],
                payload.get("body") or "",
                parent_post_id=payload.get("parent_post_id"),
                as_draft=operation == "draft",
                client_mutation_id=entity_id,
            )
            if operation == "publish" and result.get("draft"):
                result = self.post_or_draft(
                    actor,
                    payload["thread_id"],
                    payload.get("body") or "",
                    parent_post_id=payload.get("parent_post_id"),
                    as_draft=False,
                )
            return {"sync_status": "acknowledged", "revision": 1, **result}
        if entity_type == "lab_run":
            result = self.complete_lab_run(
                actor,
                payload.get("lab_id") or entity_id,
                evidence=payload.get("evidence") or {},
                artifact_hashes=payload.get("artifact_hashes") or [],
                client_mutation_id=payload.get("client_mutation_id") or entity_id,
                fabricate_hardware=bool(payload.get("fabricate_hardware")),
            )
            return {"sync_status": "acknowledged", "revision": 1, **result}
        raise ServiceError("UNKNOWN_ENTITY_TYPE", 400)
