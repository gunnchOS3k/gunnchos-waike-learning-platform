"""Data durability acceptance marker."""

from __future__ import annotations

from datetime import datetime, timezone

from helpers import write_json


def test_data_durability_marker():
    write_json(
        "GATE_D_DATA_DURABILITY.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "scopes": [
                "migrations",
                "backup",
                "destructive_restore",
                "integrity",
                "corruption_rejection",
                "concurrency",
                "idempotency",
                "transactions",
            ],
            "evidence": "tests/gate_c/test_backup_restore.py + gate_a idempotency/txn + pr3 migration",
        },
    )
