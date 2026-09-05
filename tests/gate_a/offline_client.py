"""Local-first offline store for Gate A E2E (Device A/B simulation).

Persists pending mutations until durable sync receipts are stored locally.
Never reports 'synced' before ack persistence.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


SYNC_UX = (
    "offline",
    "online",
    "pending",
    "syncing",
    "synced",
    "conflict",
    "action_required",
    "retryable_failure",
    "rejected",
)


@dataclass
class OfflineDevice:
    """Synthetic device with durable local SQLite outbox."""

    device_id: str
    db_path: Path
    client: TestClient
    token: str
    site_id: str
    section_id: str
    online: bool = True
    lease_id: str | None = None
    ux_state: str = "online"

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS local_state (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
              client_mutation_id TEXT PRIMARY KEY,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              base_revision INTEGER NOT NULL,
              operation TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              local_sequence INTEGER NOT NULL,
              sync_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              ack_receipt_json TEXT,
              ack_persisted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS local_progress (
              pack_id TEXT NOT NULL,
              lesson_id TEXT NOT NULL,
              path TEXT,
              scroll_offset REAL,
              percent_complete REAL,
              revision INTEGER,
              PRIMARY KEY (pack_id, lesson_id)
            );
            CREATE TABLE IF NOT EXISTS local_drafts (
              draft_key TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              revision INTEGER NOT NULL
            );
            """
        )
        self.conn.commit()

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def set_online(self, online: bool) -> None:
        self.online = online
        self.ux_state = "online" if online else "offline"

    def obtain_lease(self) -> dict[str, Any]:
        r = self.client.post(
            "/api/v1/sync/leases",
            headers=self.headers(),
            json={"section_id": self.section_id, "device_id": self.device_id},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        self.lease_id = data["lease_id"]
        self.conn.execute(
            "INSERT OR REPLACE INTO local_state(key, value_json) VALUES (?,?)",
            ("lease", json.dumps(data)),
        )
        self.conn.commit()
        return data

    def enqueue(
        self,
        *,
        entity_type: str,
        entity_id: str,
        operation: str,
        payload: dict[str, Any],
        base_revision: int = 0,
    ) -> str:
        mid = _id("mut")
        seq = self.conn.execute("SELECT COUNT(*) AS c FROM outbox").fetchone()["c"] + 1
        self.conn.execute(
            """
            INSERT INTO outbox(
              client_mutation_id, entity_type, entity_id, base_revision, operation,
              payload_json, local_sequence, sync_status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                mid,
                entity_type,
                entity_id,
                base_revision,
                operation,
                json.dumps(payload),
                seq,
                "pending",
                _now(),
            ),
        )
        self.conn.commit()
        self.ux_state = "pending" if self.online else "offline"
        return mid

    def save_progress_local(
        self, pack_id: str, lesson_id: str, percent: float, revision: int = 0
    ) -> str:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO local_progress(
              pack_id, lesson_id, path, scroll_offset, percent_complete, revision
            ) VALUES (?,?,?,?,?,?)
            """,
            (pack_id, lesson_id, f"/{lesson_id}", 10.0, percent, revision),
        )
        self.conn.commit()
        return self.enqueue(
            entity_type="lesson_progress",
            entity_id=lesson_id,
            operation="upsert",
            payload={
                "pack_id": pack_id,
                "lesson_id": lesson_id,
                "path": f"/{lesson_id}",
                "scroll_offset": 10.0,
                "percent_complete": percent,
            },
            base_revision=revision,
        )

    def save_draft_local(self, draft_key: str, text: str, revision: int = 0) -> str:
        payload = {"draft_key": draft_key, "text_response": text}
        self.conn.execute(
            "INSERT OR REPLACE INTO local_drafts(draft_key, payload_json, revision) VALUES (?,?,?)",
            (draft_key, json.dumps(payload), revision),
        )
        self.conn.commit()
        return self.enqueue(
            entity_type="assignment_draft",
            entity_id=draft_key,
            operation="save",
            payload=payload,
            base_revision=revision,
        )

    def restart(self) -> None:
        """Simulate app restart — reconnect DB; outbox must survive."""
        self.conn.close()
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def pending_count(self) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM outbox WHERE sync_status IN ('pending','syncing','retryable_error')"
            ).fetchone()["c"]
        )

    def acknowledged_count(self) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM outbox WHERE sync_status='acknowledged' AND ack_receipt_json IS NOT NULL"
            ).fetchone()["c"]
        )

    def sync_outbox(self) -> list[dict[str, Any]]:
        if not self.online:
            self.ux_state = "offline"
            return []
        results: list[dict[str, Any]] = []
        rows = self.conn.execute(
            "SELECT * FROM outbox WHERE sync_status IN ('pending','retryable_error') ORDER BY local_sequence"
        ).fetchall()
        for row in rows:
            self.ux_state = "syncing"
            self.conn.execute(
                "UPDATE outbox SET sync_status='syncing' WHERE client_mutation_id=?",
                (row["client_mutation_id"],),
            )
            self.conn.commit()
            body = {
                "client_mutation_id": row["client_mutation_id"],
                "site_id": self.site_id,
                "section_id": self.section_id,
                "device_id": self.device_id,
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "base_revision": row["base_revision"],
                "operation": row["operation"],
                "payload": json.loads(row["payload_json"]),
                "local_sequence": row["local_sequence"],
                "lease_id": self.lease_id,
            }
            r = self.client.post("/api/v1/sync/mutations", headers=self.headers(), json=body)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text}
            data["_http_status"] = r.status_code
            status = data.get("sync_status")
            if r.status_code == 200 and status == "acknowledged" and data.get("ack_durable"):
                # Persist ack BEFORE clearing pending — required invariant.
                receipt = data.get("receipt")
                self.conn.execute(
                    """
                    UPDATE outbox SET sync_status='acknowledged', ack_receipt_json=?, ack_persisted_at=?
                    WHERE client_mutation_id=?
                    """,
                    (json.dumps(receipt), _now(), row["client_mutation_id"]),
                )
                self.conn.commit()
                # Only after durable ack may UX show synced for this mutation.
                self.ux_state = "synced"
            elif status == "conflict" or r.status_code == 409:
                self.conn.execute(
                    "UPDATE outbox SET sync_status='conflict' WHERE client_mutation_id=?",
                    (row["client_mutation_id"],),
                )
                self.conn.commit()
                self.ux_state = "conflict"
            elif status in {"rejected", "quarantined"}:
                self.conn.execute(
                    "UPDATE outbox SET sync_status=? WHERE client_mutation_id=?",
                    (status, row["client_mutation_id"]),
                )
                self.conn.commit()
                self.ux_state = "rejected" if status == "rejected" else "action_required"
            else:
                self.conn.execute(
                    "UPDATE outbox SET sync_status='retryable_error' WHERE client_mutation_id=?",
                    (row["client_mutation_id"],),
                )
                self.conn.commit()
                self.ux_state = "retryable_failure"
            results.append(data)
        return results

    def pull(self) -> dict[str, Any]:
        r = self.client.get(
            f"/api/v1/sync/pull?section_id={self.section_id}",
            headers=self.headers(),
        )
        assert r.status_code == 200, r.text
        return r.json()

    def never_synced_without_ack(self) -> bool:
        bad = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM outbox
            WHERE sync_status='acknowledged' AND (ack_receipt_json IS NULL OR ack_persisted_at IS NULL)
            """
        ).fetchone()["c"]
        return bad == 0
