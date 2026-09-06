"""Gate A sync: offline leases, mutation ledger, receipts, conflict policy, attachments.

Authorization here is object-level. Every entry point resolves the owning section and
requires either an active learner enrollment or an assigned staff scope on *that*
section; "same site" and ``is_instructor_side`` are never sufficient on their own.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.auth import Actor
from app.modules import txn
from app.modules.assessment_lifecycle import ServiceError
from app.modules.sections import SectionService

SYNC_STATUSES = frozenset(
    {
        "pending",
        "syncing",
        "acknowledged",
        "conflict",
        "rejected",
        "retryable_error",
        "quarantined",
    }
)

ALLOWED_MIME = frozenset(
    {
        "application/octet-stream",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
        "text/markdown",
    }
)
MAX_BLOB_BYTES = 5 * 1024 * 1024
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

DEFAULT_CAPABILITIES = (
    "lesson_progress",
    "assignment_draft",
    "quiz_attempt",
    "discussion_draft",
    "lab_local",
    "attachment_queue",
)

CAPABILITY_FOR_ENTITY = {
    "lesson_progress": "lesson_progress",
    "assignment_draft": "assignment_draft",
    "quiz_attempt": "quiz_attempt",
    "discussion_draft": "discussion_draft",
    "discussion_post": "discussion_draft",
    "lab_run": "lab_local",
    "attachment": "attachment_queue",
}

# Entity types only a learner may originate for themselves.
LEARNER_OWNED_ENTITIES = frozenset(
    {"assignment_draft", "quiz_attempt", "lab_run", "attachment", "discussion_draft"}
)

CONFLICT_CODES = frozenset({"CONFLICT", "DRAFT_CONFLICT"})
QUARANTINE_CODES = frozenset(
    {"QUARANTINED", "PATH_TRAVERSAL", "MIME_DENIED", "BLOB_TOO_LARGE", "INVALID_BLOB"}
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _safe_filename(name: str) -> str:
    base = Path(name).name  # path traversal defense
    cleaned = SAFE_NAME_RE.sub("_", base).strip("._") or "attachment.bin"
    return cleaned[:180]


class ConflictWithSnapshot(ServiceError):
    """Conflict that still wants the server's current state preserved for merge UI.

    The snapshot is written *after* the failed attempt's domain writes are rolled back,
    so a conflict never leaves a partially applied mutation behind.
    """

    def __init__(self, code: str, snapshot: dict[str, Any] | None = None) -> None:
        super().__init__(code, 409)
        self.snapshot = snapshot


class SyncService:
    """Server-authoritative sync API with durable receipts and conflict policy."""

    # Replaying a mutation id from a different device is treated as reuse, not a retry.
    device_scoped_idempotency = True

    def __init__(
        self,
        conn: sqlite3.Connection,
        blob_root: Path | None = None,
        sections: SectionService | None = None,
    ) -> None:
        self.conn = conn
        self.sections = sections or SectionService(conn)
        self.blob_root = blob_root or Path(__file__).resolve().parents[2] / "data" / "blobs"
        self.blob_root.mkdir(parents=True, exist_ok=True)

    # --- offline leases -------------------------------------------------------

    def _assert_user_enabled(self, actor: Actor) -> None:
        user = self.conn.execute(
            "SELECT disabled FROM users WHERE user_id=?", (actor.actor_id,)
        ).fetchone()
        if not user or int(user["disabled"] or 0) == 1:
            raise ServiceError("USER_DISABLED", 403)

    def issue_lease(
        self,
        actor: Actor,
        section_id: str,
        device_id: str,
        ttl_hours: int = 72,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        if not device_id or not device_id.strip():
            raise ServiceError("DEVICE_ID_REQUIRED", 400)
        if ttl_hours <= 0 or ttl_hours > 24 * 30:
            raise ServiceError("INVALID_LEASE_TTL", 400)
        self._assert_user_enabled(actor)
        # Object-level: enrolled learner or assigned staff on this exact section.
        self.sections.require_section_access(actor, section_id)

        caps = list(capabilities or DEFAULT_CAPABILITIES)
        lease_id = _id("lease")
        now = datetime.now(tz=timezone.utc)
        expires = now + timedelta(hours=ttl_hours)
        self.conn.execute(
            """
            INSERT INTO offline_leases(
              lease_id, user_id, site_id, section_id, device_id,
              issued_at, expires_at, capabilities_json
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                lease_id,
                actor.actor_id,
                actor.site_id,
                section_id,
                device_id,
                now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
                json.dumps(caps),
            ),
        )
        self.conn.commit()
        return {
            "lease_id": lease_id,
            "user_id": actor.actor_id,
            "site_id": actor.site_id,
            "section_id": section_id,
            "device_id": device_id,
            "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revoked": False,
            "revoke_reason": None,
            "capabilities": caps,
        }

    def get_lease(self, lease_id: str) -> dict[str, Any] | None:
        """Unauthorized raw read — internal callers only."""
        row = self.conn.execute(
            "SELECT * FROM offline_leases WHERE lease_id=?", (lease_id,)
        ).fetchone()
        return self._lease_dict(row) if row else None

    def read_lease(self, actor: Actor, lease_id: str) -> dict[str, Any]:
        """Lease owner, or staff assigned to the lease's section. Not any same-site staff."""
        lease = self.get_lease(lease_id)
        if not lease:
            raise ServiceError("LEASE_NOT_FOUND", 404)
        self._require_lease_visibility(actor, lease)
        return lease

    def _require_lease_visibility(self, actor: Actor, lease: dict[str, Any]) -> None:
        if lease["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        if lease["user_id"] == actor.actor_id:
            return
        if self.sections.has_staff_scope(actor, lease["section_id"]):
            return
        raise ServiceError("SECTION_NOT_ASSIGNED" if actor.is_instructor_side else "FORBIDDEN", 403)

    def revoke_lease(self, actor: Actor, lease_id: str, reason: str = "revoked") -> dict[str, Any]:
        lease = self.get_lease(lease_id)
        if not lease:
            raise ServiceError("LEASE_NOT_FOUND", 404)
        if lease["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        # Revocation is a staff action scoped to the lease's own section.
        self.sections.require_staff_scope(actor, lease["section_id"])
        self.conn.execute(
            "UPDATE offline_leases SET revoked_at=?, revoke_reason=? WHERE lease_id=?",
            (_now(), reason, lease_id),
        )
        self.conn.commit()
        return self.get_lease(lease_id)  # type: ignore[return-value]

    def assert_lease_allows(
        self, actor: Actor, lease_id: str | None, capability: str, section_id: str
    ) -> dict[str, Any] | None:
        """Online sync may omit lease; offline-originated mutations must present a valid lease."""
        if lease_id is None:
            return None
        lease = self.get_lease(lease_id)
        if not lease:
            raise ServiceError("LEASE_NOT_FOUND", 403)
        if lease["user_id"] != actor.actor_id:
            raise ServiceError("LEASE_ACTOR_MISMATCH", 403)
        if lease["section_id"] != section_id:
            raise ServiceError("LEASE_SCOPE_MISMATCH", 403)
        if lease["site_id"] != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        if lease["revoked"]:
            raise ServiceError("LEASE_REVOKED", 403)
        if _parse(lease["expires_at"]) < datetime.now(tz=timezone.utc):
            raise ServiceError("LEASE_EXPIRED", 403)
        if capability not in lease["capabilities"]:
            raise ServiceError("LEASE_CAPABILITY_DENIED", 403)
        return lease

    def _lease_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "lease_id": row["lease_id"],
            "user_id": row["user_id"],
            "site_id": row["site_id"],
            "section_id": row["section_id"],
            "device_id": row["device_id"],
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "revoked": bool(row["revoked_at"]),
            "revoke_reason": row["revoke_reason"],
            "capabilities": json.loads(row["capabilities_json"] or "[]"),
        }

    # --- authorization --------------------------------------------------------

    def authorize_mutation_scope(self, actor: Actor, entity_type: str, section_id: str) -> None:
        """Authorize the section for this mutation, lease or no lease.

        A lease is a capability token, not an authorization decision: enrollment can be
        revoked while a lease is still unexpired, and a same-site instructor who was
        never assigned to the section has no standing here at all.
        """
        self._assert_user_enabled(actor)
        self.sections.require_section(actor, section_id)
        if entity_type in LEARNER_OWNED_ENTITIES:
            # Staff may act on their own assigned section (e.g. authoring demo evidence),
            # but a learner must hold a live enrollment.
            if actor.is_learner and self.sections.is_enrolled(actor.actor_id, section_id):
                return
            if self.sections.has_staff_scope(actor, section_id):
                return
            if actor.is_learner:
                raise ServiceError("ENROLLMENT_REVOKED", 403)
            raise ServiceError("SECTION_NOT_ASSIGNED", 403)
        self.sections.require_section_access(actor, section_id)

    # --- mutations + receipts -------------------------------------------------

    def _assert_idempotent_match(
        self,
        existing: sqlite3.Row,
        *,
        actor: Actor,
        site_id: str,
        section_id: str,
        device_id: str,
        entity_type: str,
        entity_id: str,
        operation: str,
        payload_hash: str,
    ) -> None:
        """A retry must be the *same* mutation; anything else is id reuse, not a replay."""
        expected = [
            (existing["actor_id"], actor.actor_id),
            (existing["site_id"], site_id),
            (existing["section_id"], section_id),
            (existing["entity_type"], entity_type),
            (existing["entity_id"], entity_id),
            (existing["operation"], operation),
            (existing["payload_hash"], payload_hash),
        ]
        if self.device_scoped_idempotency:
            expected.append((existing["device_id"], device_id))
        if any(stored != incoming for stored, incoming in expected):
            raise ServiceError("MUTATION_ID_REUSE_MISMATCH", 409)

    def apply_mutation(
        self,
        actor: Actor,
        *,
        client_mutation_id: str,
        site_id: str,
        section_id: str,
        device_id: str,
        entity_type: str,
        entity_id: str,
        base_revision: int,
        operation: str,
        payload: dict[str, Any],
        local_sequence: int = 0,
        lease_id: str | None = None,
        activity_handler: Any | None = None,
    ) -> dict[str, Any]:
        if site_id != actor.site_id:
            raise ServiceError("CROSS_SITE_DENIED", 403)
        if not client_mutation_id or len(client_mutation_id) < 8:
            raise ServiceError("INVALID_MUTATION_ID", 400)
        if not device_id:
            raise ServiceError("DEVICE_ID_REQUIRED", 400)
        if base_revision < 0:
            raise ServiceError("INVALID_BASE_REVISION", 400)

        payload_json = _canonical(payload)
        payload_hash = _sha256_text(payload_json)

        existing = self.conn.execute(
            "SELECT * FROM sync_mutations WHERE client_mutation_id=?",
            (client_mutation_id,),
        ).fetchone()
        if existing:
            self._assert_idempotent_match(
                existing,
                actor=actor,
                site_id=site_id,
                section_id=section_id,
                device_id=device_id,
                entity_type=entity_type,
                entity_id=entity_id,
                operation=operation,
                payload_hash=payload_hash,
            )
            receipt = self.conn.execute(
                "SELECT * FROM sync_receipts WHERE client_mutation_id=? AND actor_id=?",
                (client_mutation_id, actor.actor_id),
            ).fetchone()
            return {
                "client_mutation_id": client_mutation_id,
                "sync_status": existing["sync_status"],
                "idempotent_replay": True,
                "server_revision": existing["server_revision"],
                "result": json.loads(existing["result_json"] or "{}"),
                "receipt": self._receipt_dict(receipt) if receipt else None,
                "ack_durable": receipt is not None and receipt["result"] == "ok",
            }

        # Authorization happens before anything is written, with or without a lease.
        self.authorize_mutation_scope(actor, entity_type, section_id)
        if lease_id:
            self.assert_lease_allows(
                actor,
                lease_id,
                CAPABILITY_FOR_ENTITY.get(entity_type, "lesson_progress"),
                section_id,
            )

        txn.enter(self.conn, "sync_mutation")
        try:
            self.conn.execute(
                """
                INSERT INTO sync_mutations(
                  client_mutation_id, actor_id, site_id, section_id, device_id,
                  entity_type, entity_id, base_revision, operation, payload_json,
                  payload_hash, local_sequence, created_at, sync_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    client_mutation_id,
                    actor.actor_id,
                    site_id,
                    section_id,
                    device_id,
                    entity_type,
                    entity_id,
                    base_revision,
                    operation,
                    payload_json,
                    payload_hash,
                    local_sequence,
                    _now(),
                    "syncing",
                ),
            )

            snapshot: dict[str, Any] | None = None
            # Inner savepoint isolates domain writes so a rejected/conflicted mutation
            # leaves the ledger row but no partial domain state.
            txn.enter(self.conn, "sync_domain")
            try:
                result = self._dispatch(
                    actor,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    base_revision=base_revision,
                    operation=operation,
                    payload=payload,
                    section_id=section_id,
                    activity_handler=activity_handler,
                )
                status = result.get("sync_status", "acknowledged")
                server_revision = int(result.get("revision", base_revision + 1))
                txn.release(self.conn, "sync_domain")
            except ServiceError as e:
                txn.rollback(self.conn, "sync_domain")
                status = self._status_for_error(e)
                result = {"error": e.code, "status": e.status}
                server_revision = base_revision
                snapshot = getattr(e, "snapshot", None)

            if snapshot:
                # Intentional post-rollback write: preserve the authoritative version the
                # client must merge against.
                self._store_revision(
                    snapshot["entity_type"],
                    snapshot["entity_id"],
                    snapshot["revision"],
                    snapshot["actor_id"],
                    snapshot["payload"],
                )

            self.conn.execute(
                """
                UPDATE sync_mutations
                SET sync_status=?, server_revision=?, result_json=?, acknowledged_at=?
                WHERE client_mutation_id=?
                """,
                (
                    status,
                    server_revision,
                    json.dumps(result),
                    _now() if status == "acknowledged" else None,
                    client_mutation_id,
                ),
            )

            receipt = None
            if status in {"acknowledged", "conflict", "rejected", "quarantined"}:
                receipt = self._write_receipt(
                    client_mutation_id=client_mutation_id,
                    actor_id=actor.actor_id,
                    site_id=site_id,
                    section_id=section_id,
                    entity_type=entity_type,
                    entity_id=result.get("entity_id", entity_id)
                    if status == "acknowledged"
                    else entity_id,
                    authoritative_revision=server_revision,
                    result="ok" if status == "acknowledged" else status,
                    payload_hash=payload_hash,
                    detail=result,
                )
            txn.release(self.conn, "sync_mutation")
        except Exception:
            txn.rollback(self.conn, "sync_mutation")
            self.conn.commit()
            raise

        self.conn.commit()
        return {
            "client_mutation_id": client_mutation_id,
            "sync_status": status,
            "idempotent_replay": False,
            "server_revision": server_revision,
            "result": result,
            "receipt": receipt,
            # Client must persist ack before clearing pending — exposed explicitly.
            "ack_durable": status == "acknowledged" and receipt is not None,
        }

    def _status_for_error(self, e: ServiceError) -> str:
        if e.code in CONFLICT_CODES:
            return "conflict"
        if e.code in QUARANTINE_CODES:
            return "quarantined"
        return "rejected" if e.status < 500 else "retryable_error"

    def _write_receipt(self, **kwargs: Any) -> dict[str, Any]:
        receipt_id = _id("syncr")
        detail = kwargs.pop("detail", {})
        row = {
            "receipt_id": receipt_id,
            "client_mutation_id": kwargs["client_mutation_id"],
            "actor_id": kwargs["actor_id"],
            "site_id": kwargs["site_id"],
            "section_id": kwargs["section_id"],
            "entity_type": kwargs["entity_type"],
            "entity_id": kwargs["entity_id"],
            "authoritative_revision": kwargs["authoritative_revision"],
            "result": kwargs["result"],
            "payload_hash": kwargs.get("payload_hash"),
            "server_timestamp": _now(),
            "detail_json": json.dumps(detail),
        }
        self.conn.execute(
            """
            INSERT INTO sync_receipts(
              receipt_id, client_mutation_id, actor_id, site_id, section_id, entity_type,
              entity_id, authoritative_revision, result, payload_hash, server_timestamp, detail_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["receipt_id"],
                row["client_mutation_id"],
                row["actor_id"],
                row["site_id"],
                row["section_id"],
                row["entity_type"],
                row["entity_id"],
                row["authoritative_revision"],
                row["result"],
                row["payload_hash"],
                row["server_timestamp"],
                row["detail_json"],
            ),
        )
        return self._receipt_dict_from_dict(row)

    def _receipt_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "receipt_id": row["receipt_id"],
            "client_mutation_id": row["client_mutation_id"],
            "actor_id": row["actor_id"],
            "site_id": row["site_id"],
            "section_id": row["section_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "authoritative_revision": row["authoritative_revision"],
            "result": row["result"],
            "payload_hash": row["payload_hash"],
            "server_timestamp": row["server_timestamp"],
            "detail": json.loads(row["detail_json"] or "{}"),
        }

    def _receipt_dict_from_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **{k: v for k, v in row.items() if k != "detail_json"},
            "detail": json.loads(row["detail_json"] or "{}"),
        }

    def get_receipt(self, actor: Actor, client_mutation_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM sync_receipts WHERE client_mutation_id=?",
            (client_mutation_id,),
        ).fetchone()
        if not row:
            raise ServiceError("RECEIPT_NOT_FOUND", 404)
        if row["site_id"] != actor.site_id:
            # Do not confirm existence of another tenant's receipt.
            raise ServiceError("RECEIPT_NOT_FOUND", 404)
        if row["actor_id"] != actor.actor_id:
            if not self.sections.has_staff_scope(actor, row["section_id"]):
                raise ServiceError("RECEIPT_NOT_FOUND", 404)
        return self._receipt_dict(row)  # type: ignore[return-value]

    def pull_changes(
        self, actor: Actor, section_id: str, since_revision: int = 0
    ) -> dict[str, Any]:
        """Cross-device pull of authoritative entity revisions + grades/feedback for section."""
        self._assert_user_enabled(actor)
        # Revoked learners and unassigned same-site staff cannot pull.
        self.sections.require_section_access(actor, section_id)

        progress = self.conn.execute(
            """
            SELECT * FROM lesson_progress
            WHERE user_id=? AND section_id=? AND revision > ?
            ORDER BY revision
            """,
            (actor.actor_id, section_id, since_revision),
        ).fetchall()
        drafts = self.conn.execute(
            """
            SELECT * FROM draft_versions
            WHERE user_id=? AND section_id=? AND revision > ?
            ORDER BY revision
            """,
            (actor.actor_id, section_id, since_revision),
        ).fetchall()

        grades: list[dict[str, Any]] = []
        feedback: list[dict[str, Any]] = []
        if actor.is_learner:
            for g in self.conn.execute(
                """
                SELECT g.*, s.assignment_id FROM grades g
                JOIN submissions s ON s.submission_id = g.submission_id
                WHERE s.learner_id=? AND (g.section_id=? OR s.section_id=?)
                """,
                (actor.actor_id, section_id, section_id),
            ).fetchall():
                grades.append(dict(g))
            for f in self.conn.execute(
                """
                SELECT f.* FROM feedback f
                JOIN submissions s ON s.submission_id = f.submission_id
                WHERE s.learner_id=? AND s.section_id=?
                """,
                (actor.actor_id, section_id),
            ).fetchall():
                feedback.append(dict(f))

        return {
            "section_id": section_id,
            "lesson_progress": [dict(r) for r in progress],
            "draft_versions": [
                {
                    **dict(r),
                    "payload": json.loads(r["payload_json"]),
                }
                for r in drafts
            ],
            "grades": grades,
            "feedback": feedback,
            "pulled_at": _now(),
        }

    def _dispatch(
        self,
        actor: Actor,
        *,
        entity_type: str,
        entity_id: str,
        base_revision: int,
        operation: str,
        payload: dict[str, Any],
        section_id: str,
        activity_handler: Any | None,
    ) -> dict[str, Any]:
        if entity_type == "lesson_progress":
            return self._apply_lesson_progress(
                actor, entity_id, base_revision, operation, payload, section_id
            )
        if entity_type == "assignment_draft":
            return self._apply_draft(
                actor, entity_id, base_revision, operation, payload, section_id
            )
        if entity_type == "attachment":
            return self._apply_attachment(actor, entity_id, payload, section_id)
        if activity_handler is not None:
            return activity_handler.handle_sync_mutation(
                actor,
                entity_type=entity_type,
                entity_id=entity_id,
                base_revision=base_revision,
                operation=operation,
                payload=payload,
                section_id=section_id,
            )
        raise ServiceError("UNKNOWN_ENTITY_TYPE", 400)

    def _apply_lesson_progress(
        self,
        actor: Actor,
        entity_id: str,
        base_revision: int,
        operation: str,
        payload: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any]:
        pack_id = payload.get("pack_id") or "pack_dc"
        lesson_id = payload.get("lesson_id") or entity_id
        existing = self.conn.execute(
            """
            SELECT * FROM lesson_progress
            WHERE user_id=? AND section_id=? AND pack_id=? AND lesson_id=?
            """,
            (actor.actor_id, section_id, pack_id, lesson_id),
        ).fetchone()
        current_rev = int(existing["revision"]) if existing else 0
        if existing and base_revision < current_rev and operation != "force_server":
            raise ConflictWithSnapshot(
                "CONFLICT",
                snapshot={
                    "entity_type": "lesson_progress",
                    "entity_id": existing["progress_id"],
                    "revision": current_rev,
                    "actor_id": actor.actor_id,
                    "payload": {
                        "pack_id": pack_id,
                        "lesson_id": lesson_id,
                        "path": existing["path"],
                        "scroll_offset": existing["scroll_offset"],
                        "percent_complete": existing["percent_complete"],
                    },
                },
            )

        percent = float(payload.get("percent_complete") or 0)
        scroll = float(payload.get("scroll_offset") or 0)
        if not 0 <= percent <= 100 or scroll < 0:
            raise ServiceError("INVALID_PROGRESS_PAYLOAD", 400)

        progress_id = existing["progress_id"] if existing else _id("prog")
        new_rev = current_rev + 1
        path = str(payload.get("path") or "")
        now = _now()
        if existing:
            self.conn.execute(
                """
                UPDATE lesson_progress
                SET path=?, scroll_offset=?, percent_complete=?, revision=?, updated_at=?
                WHERE progress_id=?
                """,
                (path, scroll, percent, new_rev, now, progress_id),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO lesson_progress(
                  progress_id, user_id, site_id, section_id, pack_id, lesson_id,
                  path, scroll_offset, percent_complete, revision, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    progress_id,
                    actor.actor_id,
                    actor.site_id,
                    section_id,
                    pack_id,
                    lesson_id,
                    path,
                    scroll,
                    percent,
                    new_rev,
                    now,
                ),
            )
        self._store_revision(
            "lesson_progress",
            progress_id,
            new_rev,
            actor.actor_id,
            {
                "pack_id": pack_id,
                "lesson_id": lesson_id,
                "path": path,
                "scroll_offset": scroll,
                "percent_complete": percent,
            },
        )
        return {
            "sync_status": "acknowledged",
            "entity_id": progress_id,
            "revision": new_rev,
            "lesson_id": lesson_id,
            "pack_id": pack_id,
        }

    def _apply_draft(
        self,
        actor: Actor,
        entity_id: str,
        base_revision: int,
        operation: str,
        payload: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any]:
        draft_key = payload.get("draft_key") or entity_id
        latest = self.conn.execute(
            "SELECT MAX(revision) AS rev FROM draft_versions WHERE draft_key=? AND user_id=?",
            (draft_key, actor.actor_id),
        ).fetchone()
        current_rev = int(latest["rev"] or 0)
        if current_rev and base_revision < current_rev:
            # Never silent overwrite — preserve prior version, signal conflict.
            raise ServiceError("DRAFT_CONFLICT", 409)
        new_rev = current_rev + 1
        version_id = _id("dver")
        payload_json = _canonical(payload)
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
                "assignment_draft",
                entity_id,
                actor.actor_id,
                section_id,
                new_rev,
                payload_json,
                _sha256_text(payload_json),
                _now(),
            ),
        )
        return {
            "sync_status": "acknowledged",
            "entity_id": draft_key,
            "version_id": version_id,
            "revision": new_rev,
            "preserved_prior": current_rev > 0,
        }

    # --- attachments ----------------------------------------------------------

    def _blob_path(self, site_id: str, section_id: str, content_hash: str, safe: str) -> Path:
        """Resolve under blob_root using containment, not string prefixes."""
        root = self.blob_root.resolve()
        for component in (site_id, section_id):
            if not PATH_COMPONENT_RE.match(component or ""):
                raise ServiceError("PATH_TRAVERSAL", 400)
        candidate = (root / site_id / section_id / f"{content_hash[:16]}_{safe}").resolve()
        try:
            candidate.relative_to(root)
        except ValueError as e:
            raise ServiceError("PATH_TRAVERSAL", 400) from e
        return candidate

    def _apply_attachment(
        self,
        actor: Actor,
        entity_id: str,
        payload: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any]:
        filename = str(payload.get("filename") or "file.bin")
        if (
            "/" in filename
            or "\\" in filename
            or ".." in filename
            or filename.startswith("~")
            or Path(filename).is_absolute()
        ):
            raise ServiceError("PATH_TRAVERSAL", 400)
        mime = str(payload.get("mime_type") or "application/octet-stream")
        if mime not in ALLOWED_MIME:
            raise ServiceError("MIME_DENIED", 400)
        raw_b64 = payload.get("content_base64") or ""
        try:
            data = base64.b64decode(raw_b64, validate=True)
        except Exception as e:
            raise ServiceError("INVALID_BLOB", 400) from e
        if len(data) > MAX_BLOB_BYTES:
            raise ServiceError("BLOB_TOO_LARGE", 400)
        content_hash = _sha256_bytes(data)
        claimed = payload.get("content_hash")
        if claimed and claimed != content_hash:
            raise ServiceError("HASH_MISMATCH", 400)

        # Dedup is tenancy-scoped: another site's identical bytes are a different blob.
        existing = self.conn.execute(
            "SELECT * FROM attachment_blobs WHERE site_id=? AND content_hash=?",
            (actor.site_id, content_hash),
        ).fetchone()
        if existing:
            # Authorize the section the blob is actually persisted under before returning it.
            persisted_section = existing["section_id"]
            if persisted_section != section_id:
                try:
                    self.sections.require_section_access(actor, persisted_section)
                except ServiceError as e:
                    raise ServiceError("ATTACHMENT_SCOPE_DENIED", 403) from e
            return {
                "sync_status": "acknowledged",
                "entity_id": existing["blob_id"],
                "revision": 1,
                "content_hash": content_hash,
                "site_id": existing["site_id"],
                "section_id": persisted_section,
                "deduplicated": True,
                "quarantined": bool(existing["quarantined"]),
            }

        safe = _safe_filename(filename)
        blob_id = _id("blob")
        storage = self._blob_path(actor.site_id, section_id, content_hash, safe)
        storage.parent.mkdir(parents=True, exist_ok=True)
        storage.write_bytes(data)
        quarantine = 1 if payload.get("force_quarantine") else 0
        reason = "policy" if quarantine else None
        self.conn.execute(
            """
            INSERT INTO attachment_blobs(
              blob_id, content_hash, filename, safe_filename, mime_type, byte_size,
              storage_path, quarantined, quarantine_reason, uploaded_by, site_id,
              section_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                blob_id,
                content_hash,
                filename,
                safe,
                mime,
                len(data),
                str(storage),
                quarantine,
                reason,
                actor.actor_id,
                actor.site_id,
                section_id,
                _now(),
            ),
        )
        return {
            # A quarantined blob is deliberately retained as evidence, so it returns a
            # status rather than raising — raising would roll the record back.
            "sync_status": "quarantined" if quarantine else "acknowledged",
            "quarantined": bool(quarantine),
            "quarantine_reason": reason,
            "entity_id": blob_id,
            "revision": 1,
            "content_hash": content_hash,
            "site_id": actor.site_id,
            "section_id": section_id,
            "byte_size": len(data),
            "safe_filename": safe,
            "deduplicated": False,
        }

    def _store_revision(
        self,
        entity_type: str,
        entity_id: str,
        revision: int,
        actor_id: str,
        payload: dict[str, Any],
    ) -> None:
        payload_json = _canonical(payload)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO entity_revisions(
              entity_type, entity_id, revision, actor_id, payload_json, payload_hash, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                entity_type,
                entity_id,
                revision,
                actor_id,
                payload_json,
                _sha256_text(payload_json),
                _now(),
            ),
        )
