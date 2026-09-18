"""Hub telemetry — explicit metrics export over Observability (Stream B exhaustion).

Observability already records redacted events. This module adds:
- named telemetry event types (sync/ack/assessment/ai)
- counter rollups for operator diagnostics
- fail-closed access (site admin / instructor-side only)

Not a claim of production APM or field-pilot telemetry.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.auth import Actor
from app.modules.assessment_lifecycle import ServiceError, _id, _now, _rows
from app.modules.hardening import Observability, redact_obj, redact_text

TELEMETRY_CATEGORIES = frozenset(
    {
        "sync_outbox",
        "sync_ack",
        "conflict",
        "assessment",
        "quiz",
        "assignment",
        "lab",
        "gradebook",
        "ai_assist",
        "backup",
        "export",
        "auth",
        "a11y",
        "deviceos",
    }
)


class TelemetryService:
    """Thin, auditable telemetry façade over observability_events."""

    def __init__(self, conn: sqlite3.Connection, observability: Observability | None = None) -> None:
        self.conn = conn
        self.obs = observability or Observability(conn)

    def emit(
        self,
        *,
        category: str,
        message: str,
        level: str = "info",
        detail: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> str:
        if category not in TELEMETRY_CATEGORIES:
            raise ServiceError("TELEMETRY_CATEGORY_INVALID", 400)
        payload = redact_obj({"actor_id": actor_id, **(detail or {})})
        # Prefer Observability.emit for redaction + persistence.
        return self.obs.emit(level, f"telemetry.{category}", redact_text(message), payload)

    def counters(self, actor: Actor, *, limit: int = 50) -> dict[str, Any]:
        if not (actor.is_site_admin or actor.is_instructor_side):
            raise ServiceError("TELEMETRY_FORBIDDEN", 403)
        rows = _rows(
            self.conn,
            """
            SELECT category, COUNT(*) AS n
            FROM observability_events
            WHERE category LIKE 'telemetry.%'
            GROUP BY category
            ORDER BY n DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent = _rows(
            self.conn,
            """
            SELECT event_id, level, category, message, created_at
            FROM observability_events
            WHERE category LIKE 'telemetry.%'
            ORDER BY created_at DESC
            LIMIT 20
            """,
        )
        return {
            "schema": "waike.telemetry.counters.v1",
            "counters": {r["category"]: int(r["n"]) for r in rows},
            "recent": [dict(r) for r in recent],
            "claim_boundary": "Digital hub metrics only; not learner field evidence.",
        }

    def seed_synthetic_smoke(self, actor: Actor) -> dict[str, Any]:
        """SYNTHETIC fixture emissions for automated exhaustion tests."""
        if not actor.is_site_admin:
            raise ServiceError("TELEMETRY_FORBIDDEN", 403)
        ids = [
            self.emit(
                category="sync_outbox",
                message="SYNTHETIC outbox enqueue",
                detail={"label": "SYNTHETIC", "entity": "quiz_attempt"},
                actor_id=actor.actor_id,
            ),
            self.emit(
                category="sync_ack",
                message="SYNTHETIC ack",
                detail={"label": "SYNTHETIC", "status": "acknowledged"},
                actor_id=actor.actor_id,
            ),
            self.emit(
                category="conflict",
                message="SYNTHETIC conflict recorded",
                detail={"label": "SYNTHETIC", "code": "DRAFT_CONFLICT"},
                actor_id=actor.actor_id,
            ),
        ]
        return {"label": "SYNTHETIC", "event_ids": ids}
