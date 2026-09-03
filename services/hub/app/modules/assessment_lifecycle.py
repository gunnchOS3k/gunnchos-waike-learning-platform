from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.auth import Actor, Role, SYNTHETIC_ACTORS


SCHEMA_VERSION = "1.0.0"
MODULE_ID = "DIGITAL_CONFIDENCE"
MASTERY_THRESHOLD = 3.0


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def _audit(conn: sqlite3.Connection, actor_id: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_events(event_id, actor_id, action, entity_type, entity_id, detail_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (_id("aud"), actor_id, action, entity_type, entity_id, json.dumps(detail or {}), _now()),
    )


@dataclass
class ServiceError(Exception):
    code: str
    status: int = 400

    def __str__(self) -> str:
        return self.code


class AssessmentService:
    """Modular-monolith assessment lifecycle (assignments → portfolio)."""

    def __init__(self, conn: sqlite3.Connection, waike_root: Path | None = None, source_commit: str = "") -> None:
        self.conn = conn
        self.waike_root = waike_root
        self.source_commit = source_commit

    # --- seed -----------------------------------------------------------------
    def seed_synthetic_actors(self) -> None:
        for actor_id, meta in SYNTHETIC_ACTORS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO actors(actor_id, role, display_name) VALUES (?,?,?)",
                (actor_id, meta["role"], meta["display_name"]),
            )
        self.conn.commit()

    def seed_digital_confidence_assignment(self) -> dict[str, Any]:
        """Load a REAL WAIKE DIGITAL_CONFIDENCE assignment — never invent curriculum."""
        if self.waike_root is None:
            raise ServiceError("WAIKE_ROOT_REQUIRED", 500)
        assign_path = self.waike_root / "assignments/by_course/digital_confidence/week_01.yaml"
        body_path = self.waike_root / "assignment_bodies/by_course/digital_confidence/assignment_01.md"
        rubric_path = self.waike_root / "rubrics/master_rubric.yaml"
        if not assign_path.is_file():
            raise ServiceError("WAIKE_ASSIGNMENT_MISSING", 500)
        if not body_path.is_file():
            raise ServiceError("WAIKE_ASSIGNMENT_BODY_MISSING", 500)
        if not rubric_path.is_file():
            raise ServiceError("WAIKE_RUBRIC_MISSING", 500)

        assign = yaml.safe_load(assign_path.read_text(encoding="utf-8"))
        body = body_path.read_text(encoding="utf-8")
        rubric_yaml = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))

        assignment_id = str(assign["assignment_id"])
        title = str(assign["assignment_title"])
        existing = _row(self.conn, "SELECT assignment_id FROM assignments WHERE assignment_id=?", (assignment_id,))
        if existing:
            return self.get_assignment(assignment_id)

        outcome_id = "outcome_dc_w01_reflection"
        self.conn.execute(
            "INSERT OR IGNORE INTO outcomes(outcome_id, module_id, code, title, description) VALUES (?,?,?,?,?)",
            (
                outcome_id,
                MODULE_ID,
                "DC-W01-REFLECT",
                "Digital confidence community reflection",
                "Learner articulates what digital confidence means in community context.",
            ),
        )

        rubric_id = "rubric_master_waike_v1"
        self.conn.execute(
            "INSERT OR IGNORE INTO rubrics(rubric_id, schema_version, title, source_path, source_commit) VALUES (?,?,?,?,?)",
            (
                rubric_id,
                SCHEMA_VERSION,
                "WAIKE master rubric",
                str(rubric_path.relative_to(self.waike_root)),
                self.source_commit,
            ),
        )
        # Clear/rebuild criteria for determinism if re-seeded into empty DB
        scale = rubric_yaml.get("scale") or {}
        categories = list(rubric_yaml.get("categories") or [])
        # For PR2 digital confidence reflection, score the first five categories (real WAIKE categories).
        for idx, cat in enumerate(categories[:5]):
            criterion_id = f"crit_{cat}"
            self.conn.execute(
                "INSERT OR IGNORE INTO rubric_criteria(criterion_id, rubric_id, description, max_points, sort_order) VALUES (?,?,?,?,?)",
                (criterion_id, rubric_id, cat.replace("_", " "), 4.0, idx),
            )
            for score, label in sorted(((int(k), v) for k, v in scale.items()), reverse=True):
                level_id = f"{criterion_id}_L{score}"
                self.conn.execute(
                    "INSERT OR IGNORE INTO rubric_levels(level_id, criterion_id, score, label, description) VALUES (?,?,?,?,?)",
                    (level_id, criterion_id, float(score), f"Level {score}", str(label)),
                )

        content_hash = _sha256_text(title + "\n" + body)
        now = _now()
        self.conn.execute(
            """
            INSERT INTO assignments(
              assignment_id, module_id, schema_version, title, week, body_markdown,
              source_path, source_commit, rubric_id, outcome_id, mastery_threshold,
              portfolio_connection, revision_policy, current_version, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                assignment_id,
                MODULE_ID,
                SCHEMA_VERSION,
                title,
                int(assign.get("week") or 1),
                body,
                str(assign_path.relative_to(self.waike_root)),
                self.source_commit,
                rubric_id,
                outcome_id,
                MASTERY_THRESHOLD,
                1 if assign.get("portfolio_connection") else 0,
                str(assign.get("revision_policy") or "allowed_with_changelog"),
                1,
                now,
            ),
        )
        version_id = _id("asgv")
        self.conn.execute(
            """
            INSERT INTO assignment_versions(
              assignment_version_id, assignment_id, version, title, body_markdown, rubric_id, content_hash, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (version_id, assignment_id, 1, title, body, rubric_id, content_hash, now),
        )
        _audit(self.conn, "system", "seed_assignment", "assignment", assignment_id, {"source": str(assign_path)})
        self.conn.commit()
        return self.get_assignment(assignment_id)

    # --- assignments ----------------------------------------------------------
    def list_assignments(self, actor: Actor) -> list[dict[str, Any]]:
        rows = _rows(
            self.conn,
            "SELECT assignment_id, module_id, title, week, current_version, portfolio_connection FROM assignments ORDER BY week, assignment_id",
        )
        return [dict(r) for r in rows]

    def get_assignment(self, assignment_id: str) -> dict[str, Any]:
        row = _row(self.conn, "SELECT * FROM assignments WHERE assignment_id=?", (assignment_id,))
        if not row:
            raise ServiceError("ASSIGNMENT_NOT_FOUND", 404)
        criteria = _rows(
            self.conn,
            "SELECT criterion_id, description, max_points, sort_order FROM rubric_criteria WHERE rubric_id=? ORDER BY sort_order",
            (row["rubric_id"],),
        )
        levels = {}
        for c in criteria:
            levels[c["criterion_id"]] = [
                dict(l)
                for l in _rows(
                    self.conn,
                    "SELECT level_id, score, label, description FROM rubric_levels WHERE criterion_id=? ORDER BY score DESC",
                    (c["criterion_id"],),
                )
            ]
        return {
            **dict(row),
            "rubric": {
                "rubric_id": row["rubric_id"],
                "criteria": [
                    {**dict(c), "levels": levels.get(c["criterion_id"], [])} for c in criteria
                ],
            },
        }

    # --- drafts ---------------------------------------------------------------
    def save_draft(
        self,
        actor: Actor,
        assignment_id: str,
        text_response: str,
        artifact_name: str | None = None,
        artifact_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        self.get_assignment(assignment_id)
        existing = _row(
            self.conn,
            "SELECT * FROM drafts WHERE assignment_id=? AND learner_id=?",
            (assignment_id, actor.actor_id),
        )
        art_sha = _sha256_bytes(artifact_bytes) if artifact_bytes is not None else None
        now = _now()
        if existing:
            rev = int(existing["revision"]) + 1
            self.conn.execute(
                """
                UPDATE drafts SET text_response=?, artifact_name=?, artifact_bytes=?, artifact_sha256=?, revision=?, updated_at=?
                WHERE draft_id=?
                """,
                (
                    text_response,
                    artifact_name if artifact_name is not None else existing["artifact_name"],
                    artifact_bytes if artifact_bytes is not None else existing["artifact_bytes"],
                    art_sha if artifact_bytes is not None else existing["artifact_sha256"],
                    rev,
                    now,
                    existing["draft_id"],
                ),
            )
            draft_id = existing["draft_id"]
        else:
            draft_id = _id("draft")
            self.conn.execute(
                """
                INSERT INTO drafts(draft_id, assignment_id, learner_id, text_response, artifact_name, artifact_bytes, artifact_sha256, revision, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    draft_id,
                    assignment_id,
                    actor.actor_id,
                    text_response,
                    artifact_name,
                    artifact_bytes,
                    art_sha,
                    1,
                    now,
                ),
            )
        _audit(self.conn, actor.actor_id, "draft_autosave", "draft", draft_id, {"assignment_id": assignment_id})
        self.conn.commit()
        return self.get_draft(actor, assignment_id)

    def get_draft(self, actor: Actor, assignment_id: str) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        row = _row(
            self.conn,
            "SELECT draft_id, assignment_id, learner_id, text_response, artifact_name, artifact_sha256, revision, updated_at FROM drafts WHERE assignment_id=? AND learner_id=?",
            (assignment_id, actor.actor_id),
        )
        if not row:
            return {
                "draft_id": None,
                "assignment_id": assignment_id,
                "learner_id": actor.actor_id,
                "text_response": "",
                "artifact_name": None,
                "artifact_sha256": None,
                "revision": 0,
                "updated_at": None,
            }
        return dict(row)

    # --- submit ---------------------------------------------------------------
    def submit(
        self,
        actor: Actor,
        assignment_id: str,
        idempotency_key: str,
        text_response: str | None = None,
        artifact_name: str | None = None,
        artifact_bytes: bytes | None = None,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        if not idempotency_key:
            raise ServiceError("IDEMPOTENCY_KEY_REQUIRED", 400)

        prior = _row(
            self.conn,
            "SELECT submission_id FROM submissions WHERE learner_id=? AND idempotency_key=?",
            (actor.actor_id, idempotency_key),
        )
        if prior:
            return self.get_submission(actor, prior["submission_id"])

        assignment = self.get_assignment(assignment_id)
        draft = self.get_draft(actor, assignment_id)
        text = text_response if text_response is not None else draft["text_response"]
        if not (text or "").strip():
            raise ServiceError("EMPTY_SUBMISSION", 400)

        # Resolve artifact: explicit upload wins, else draft artifact bytes
        art_name = artifact_name
        art_bytes = artifact_bytes
        if art_bytes is None and draft.get("draft_id"):
            drow = _row(
                self.conn,
                "SELECT artifact_name, artifact_bytes FROM drafts WHERE draft_id=?",
                (draft["draft_id"],),
            )
            if drow and drow["artifact_bytes"] is not None:
                art_name = art_name or drow["artifact_name"]
                art_bytes = bytes(drow["artifact_bytes"])

        attempt = (
            _row(
                self.conn,
                "SELECT COALESCE(MAX(attempt_number),0) AS m FROM submissions WHERE assignment_id=? AND learner_id=?",
                (assignment_id, actor.actor_id),
            )["m"]
            + 1
        )
        content_hash = _sha256_text(text)
        if art_bytes is not None:
            content_hash = _sha256_text(text + "\n" + _sha256_bytes(art_bytes))

        now = _now()
        submission_id = _id("sub")
        self.conn.execute(
            """
            INSERT INTO submissions(
              submission_id, assignment_id, assignment_version, learner_id, attempt_number,
              status, text_response, content_hash, idempotency_key, submitted_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                submission_id,
                assignment_id,
                int(assignment["current_version"]),
                actor.actor_id,
                attempt,
                "submitted",
                text,
                content_hash,
                idempotency_key,
                now,
            ),
        )
        revision_id = _id("srev")
        self.conn.execute(
            """
            INSERT INTO submission_revisions(revision_id, submission_id, revision_number, text_response, content_hash, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (revision_id, submission_id, 1, text, content_hash, now),
        )
        if art_bytes is not None:
            self.conn.execute(
                """
                INSERT INTO submission_artifacts(artifact_id, submission_id, filename, content_type, sha256, byte_size, blob)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    _id("art"),
                    submission_id,
                    art_name or "artifact.bin",
                    content_type,
                    _sha256_bytes(art_bytes),
                    len(art_bytes),
                    art_bytes,
                ),
            )
        payload = {
            "receipt_schema": SCHEMA_VERSION,
            "submission_id": submission_id,
            "assignment_id": assignment_id,
            "learner_id": actor.actor_id,
            "attempt_number": attempt,
            "content_hash": content_hash,
            "issued_at": now,
        }
        receipt_id = _id("rcpt")
        self.conn.execute(
            """
            INSERT INTO submission_receipts(receipt_id, submission_id, content_hash, issued_at, immutable_payload)
            VALUES (?,?,?,?,?)
            """,
            (receipt_id, submission_id, content_hash, now, json.dumps(payload, sort_keys=True)),
        )
        _audit(self.conn, actor.actor_id, "submit", "submission", submission_id, {"attempt": attempt})
        self.conn.commit()
        return self.get_submission(actor, submission_id)

    def get_submission(self, actor: Actor, submission_id: str) -> dict[str, Any]:
        row = _row(self.conn, "SELECT * FROM submissions WHERE submission_id=?", (submission_id,))
        if not row:
            raise ServiceError("SUBMISSION_NOT_FOUND", 404)
        if actor.is_learner and row["learner_id"] != actor.actor_id:
            raise ServiceError("FORBIDDEN_OTHER_LEARNER", 403)
        arts = [
            {
                "artifact_id": a["artifact_id"],
                "filename": a["filename"],
                "content_type": a["content_type"],
                "sha256": a["sha256"],
                "byte_size": a["byte_size"],
            }
            for a in _rows(
                self.conn,
                "SELECT artifact_id, filename, content_type, sha256, byte_size FROM submission_artifacts WHERE submission_id=?",
                (submission_id,),
            )
        ]
        receipt = _row(self.conn, "SELECT * FROM submission_receipts WHERE submission_id=?", (submission_id,))
        grade = _row(self.conn, "SELECT * FROM grades WHERE submission_id=?", (submission_id,))
        feedback = [
            dict(f)
            for f in _rows(
                self.conn,
                "SELECT feedback_id, author_id, body, created_at FROM feedback WHERE submission_id=? AND visible_to_learner=1 ORDER BY created_at",
                (submission_id,),
            )
        ]
        evaluations = [
            dict(e)
            for e in _rows(
                self.conn,
                "SELECT evaluation_id, criterion_id, level_id, points, comment, graded_by, graded_at FROM rubric_evaluations WHERE submission_id=?",
                (submission_id,),
            )
        ]
        # Hide instructor-only fields from learners beyond returned grade/feedback
        out = {
            "submission_id": row["submission_id"],
            "assignment_id": row["assignment_id"],
            "assignment_version": row["assignment_version"],
            "learner_id": row["learner_id"],
            "attempt_number": row["attempt_number"],
            "status": row["status"],
            "text_response": row["text_response"],
            "content_hash": row["content_hash"],
            "submitted_at": row["submitted_at"],
            "artifacts": arts,
            "receipt": dict(receipt) if receipt else None,
            "evaluations": evaluations if (actor.is_instructor_side or (grade and grade["returned"])) else [],
            "grade": dict(grade) if grade and (actor.is_instructor_side or grade["returned"]) else None,
            "feedback": feedback if (actor.is_instructor_side or (grade and grade["returned"])) else [],
        }
        return out

    def submission_history(self, actor: Actor, assignment_id: str) -> list[dict[str, Any]]:
        if not actor.is_learner:
            raise ServiceError("LEARNER_ROLE_REQUIRED", 403)
        rows = _rows(
            self.conn,
            "SELECT submission_id, attempt_number, status, content_hash, submitted_at FROM submissions WHERE assignment_id=? AND learner_id=? ORDER BY attempt_number",
            (assignment_id, actor.actor_id),
        )
        return [dict(r) for r in rows]

    # --- instructor queue / grade --------------------------------------------
    def instructor_queue(self, actor: Actor, assignment_id: str) -> list[dict[str, Any]]:
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        self.get_assignment(assignment_id)
        rows = _rows(
            self.conn,
            """
            SELECT s.submission_id, s.learner_id, s.attempt_number, s.status, s.submitted_at, s.content_hash,
                   g.returned AS grade_returned
            FROM submissions s
            LEFT JOIN grades g ON g.submission_id = s.submission_id
            WHERE s.assignment_id=?
            ORDER BY s.submitted_at
            """,
            (assignment_id,),
        )
        return [dict(r) for r in rows]

    def grade_submission(
        self,
        actor: Actor,
        submission_id: str,
        criterion_scores: list[dict[str, Any]],
        feedback_body: str,
        return_to_learner: bool = True,
        force_mastery_gap: bool | None = None,
    ) -> dict[str, Any]:
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        sub = _row(self.conn, "SELECT * FROM submissions WHERE submission_id=?", (submission_id,))
        if not sub:
            raise ServiceError("SUBMISSION_NOT_FOUND", 404)
        assignment = self.get_assignment(sub["assignment_id"])
        existing_grade = _row(self.conn, "SELECT * FROM grades WHERE submission_id=?", (submission_id,))

        now = _now()
        points_earned = 0.0
        points_possible = 0.0
        # Replace evaluations for this grading pass
        self.conn.execute("DELETE FROM rubric_evaluations WHERE submission_id=?", (submission_id,))
        for item in criterion_scores:
            criterion_id = item["criterion_id"]
            points = float(item["points"])
            comment = str(item.get("comment") or "")
            level_id = item.get("level_id")
            crit = _row(self.conn, "SELECT * FROM rubric_criteria WHERE criterion_id=?", (criterion_id,))
            if not crit or crit["rubric_id"] != assignment["rubric_id"]:
                raise ServiceError("INVALID_CRITERION", 400)
            points_possible += float(crit["max_points"])
            points_earned += points
            self.conn.execute(
                """
                INSERT INTO rubric_evaluations(evaluation_id, submission_id, criterion_id, level_id, points, comment, graded_by, graded_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (_id("eval"), submission_id, criterion_id, level_id, points, comment, actor.actor_id, now),
            )

        if existing_grade:
            before = dict(existing_grade)
            rev = int(existing_grade["revision"]) + 1
            self.conn.execute(
                """
                UPDATE grades SET points_earned=?, points_possible=?, returned=?, graded_by=?, graded_at=?, revision=?
                WHERE grade_id=?
                """,
                (
                    points_earned,
                    points_possible,
                    1 if return_to_learner else 0,
                    actor.actor_id,
                    now,
                    rev,
                    existing_grade["grade_id"],
                ),
            )
            grade_id = existing_grade["grade_id"]
            after = dict(_row(self.conn, "SELECT * FROM grades WHERE grade_id=?", (grade_id,)))
            self.conn.execute(
                """
                INSERT INTO grade_audit(audit_id, grade_id, actor_id, action, before_json, after_json, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    _id("gaud"),
                    grade_id,
                    actor.actor_id,
                    "revise_grade",
                    json.dumps({k: before[k] for k in before.keys()}),
                    json.dumps({k: after[k] for k in after.keys()}),
                    now,
                ),
            )
        else:
            grade_id = _id("grd")
            self.conn.execute(
                """
                INSERT INTO grades(grade_id, submission_id, learner_id, assignment_id, points_earned, points_possible, returned, graded_by, graded_at, revision)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    grade_id,
                    submission_id,
                    sub["learner_id"],
                    sub["assignment_id"],
                    points_earned,
                    points_possible,
                    1 if return_to_learner else 0,
                    actor.actor_id,
                    now,
                    1,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO grade_audit(audit_id, grade_id, actor_id, action, before_json, after_json, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    _id("gaud"),
                    grade_id,
                    actor.actor_id,
                    "create_grade",
                    None,
                    json.dumps({"points_earned": points_earned, "points_possible": points_possible}),
                    now,
                ),
            )

        if feedback_body.strip():
            self.conn.execute(
                """
                INSERT INTO feedback(feedback_id, submission_id, author_id, body, visible_to_learner, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (_id("fb"), submission_id, actor.actor_id, feedback_body, 1 if return_to_learner else 0, now),
            )

        self.conn.execute(
            "UPDATE submissions SET status=? WHERE submission_id=?",
            ("returned" if return_to_learner else "graded", submission_id),
        )

        # Gradebook
        self.conn.execute(
            """
            INSERT INTO gradebook_entries(entry_id, learner_id, assignment_id, grade_id, points_earned, points_possible, status, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(learner_id, assignment_id) DO UPDATE SET
              grade_id=excluded.grade_id,
              points_earned=excluded.points_earned,
              points_possible=excluded.points_possible,
              status=excluded.status,
              updated_at=excluded.updated_at
            """,
            (
                _id("gbe"),
                sub["learner_id"],
                sub["assignment_id"],
                grade_id,
                points_earned,
                points_possible,
                "returned" if return_to_learner else "graded",
                now,
            ),
        )

        # Mastery: average criterion points vs threshold
        avg = points_earned / max(len(criterion_scores), 1)
        threshold = float(assignment["mastery_threshold"])
        if force_mastery_gap is True:
            mastered = False
        elif force_mastery_gap is False:
            mastered = True
        else:
            mastered = avg >= threshold
        mastery_id = _id("mst")
        gap = "" if mastered else f"Average {avg:.2f} below threshold {threshold}"
        self.conn.execute(
            """
            INSERT INTO mastery_records(mastery_id, learner_id, outcome_id, assignment_id, submission_id, score, threshold, mastered, gap_notes, evaluated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mastery_id,
                sub["learner_id"],
                assignment["outcome_id"],
                sub["assignment_id"],
                submission_id,
                avg,
                threshold,
                1 if mastered else 0,
                gap,
                now,
            ),
        )

        remediation = None
        if not mastered:
            plan_id = _id("rem")
            task = (
                f"Remediation for {assignment['title']}: revise your reflection to strengthen "
                f"conceptual understanding and documentation quality. Address: {gap}"
            )
            self.conn.execute(
                """
                INSERT INTO remediation_plans(plan_id, learner_id, assignment_id, mastery_id, task_markdown, status, created_by, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (plan_id, sub["learner_id"], sub["assignment_id"], mastery_id, task, "assigned", actor.actor_id, now),
            )
            remediation = dict(_row(self.conn, "SELECT * FROM remediation_plans WHERE plan_id=?", (plan_id,)))

        portfolio = None
        if mastered and int(assignment["portfolio_connection"]) == 1:
            portfolio_id = _id("port")
            self.conn.execute(
                """
                INSERT INTO portfolio_artifacts(portfolio_id, learner_id, assignment_id, submission_id, title, evidence_hash, created_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(learner_id, submission_id) DO UPDATE SET
                  title=excluded.title,
                  evidence_hash=excluded.evidence_hash,
                  created_at=excluded.created_at
                """,
                (
                    portfolio_id,
                    sub["learner_id"],
                    sub["assignment_id"],
                    submission_id,
                    f"Portfolio evidence — {assignment['title']}",
                    sub["content_hash"],
                    now,
                ),
            )
            portfolio = dict(
                _row(
                    self.conn,
                    "SELECT * FROM portfolio_artifacts WHERE learner_id=? AND submission_id=?",
                    (sub["learner_id"], submission_id),
                )
            )
            # Complete open remediation if any
            self.conn.execute(
                """
                UPDATE remediation_plans SET status='completed', completed_at=?
                WHERE learner_id=? AND assignment_id=? AND status='assigned'
                """,
                (now, sub["learner_id"], sub["assignment_id"]),
            )

        _audit(self.conn, actor.actor_id, "grade", "submission", submission_id, {"grade_id": grade_id, "mastered": mastered})
        self.conn.commit()
        return {
            "grade": dict(_row(self.conn, "SELECT * FROM grades WHERE grade_id=?", (grade_id,))),
            "mastery": dict(_row(self.conn, "SELECT * FROM mastery_records WHERE mastery_id=?", (mastery_id,))),
            "remediation": remediation,
            "portfolio": portfolio,
            "submission": self.get_submission(actor, submission_id),
        }

    def list_remediation(self, actor: Actor) -> list[dict[str, Any]]:
        if actor.is_learner:
            rows = _rows(
                self.conn,
                "SELECT * FROM remediation_plans WHERE learner_id=? ORDER BY created_at",
                (actor.actor_id,),
            )
        elif actor.is_instructor_side:
            rows = _rows(self.conn, "SELECT * FROM remediation_plans ORDER BY created_at")
        else:
            raise ServiceError("FORBIDDEN", 403)
        return [dict(r) for r in rows]

    def list_portfolio(self, actor: Actor, learner_id: str | None = None) -> list[dict[str, Any]]:
        if actor.is_learner:
            target = actor.actor_id
        elif actor.is_instructor_side:
            target = learner_id or actor.actor_id
        else:
            raise ServiceError("FORBIDDEN", 403)
        if actor.is_learner and learner_id and learner_id != actor.actor_id:
            raise ServiceError("FORBIDDEN_OTHER_LEARNER", 403)
        rows = _rows(
            self.conn,
            "SELECT portfolio_id, learner_id, assignment_id, submission_id, title, evidence_hash, created_at FROM portfolio_artifacts WHERE learner_id=? ORDER BY created_at",
            (target,),
        )
        return [dict(r) for r in rows]

    def gradebook(self, actor: Actor, learner_id: str | None = None) -> list[dict[str, Any]]:
        if actor.is_learner:
            rows = _rows(
                self.conn,
                "SELECT * FROM gradebook_entries WHERE learner_id=? ORDER BY updated_at",
                (actor.actor_id,),
            )
        elif actor.is_instructor_side:
            if learner_id:
                rows = _rows(
                    self.conn,
                    "SELECT * FROM gradebook_entries WHERE learner_id=? ORDER BY updated_at",
                    (learner_id,),
                )
            else:
                rows = _rows(self.conn, "SELECT * FROM gradebook_entries ORDER BY learner_id, updated_at")
        else:
            raise ServiceError("FORBIDDEN", 403)
        return [dict(r) for r in rows]

    def latest_mastery(self, actor: Actor, assignment_id: str, learner_id: str | None = None) -> dict[str, Any] | None:
        target = learner_id or actor.actor_id
        if actor.is_learner and target != actor.actor_id:
            raise ServiceError("FORBIDDEN_OTHER_LEARNER", 403)
        # Prefer mastery tied to the highest submission attempt (not a regrade of an older attempt).
        row = _row(
            self.conn,
            """
            SELECT m.* FROM mastery_records m
            JOIN submissions s ON s.submission_id = m.submission_id
            WHERE m.learner_id=? AND m.assignment_id=?
            ORDER BY s.attempt_number DESC, m.evaluated_at DESC
            LIMIT 1
            """,
            (target, assignment_id),
        )
        return dict(row) if row else None

    def grade_audit_trail(self, actor: Actor, grade_id: str) -> list[dict[str, Any]]:
        if not actor.is_instructor_side:
            raise ServiceError("INSTRUCTOR_ROLE_REQUIRED", 403)
        rows = _rows(
            self.conn,
            "SELECT * FROM grade_audit WHERE grade_id=? ORDER BY created_at",
            (grade_id,),
        )
        return [dict(r) for r in rows]
