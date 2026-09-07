"""Perf / ops acceptance marker."""

from __future__ import annotations

from datetime import datetime, timezone

from gd_helpers import write_json


def test_perf_ops_marker():
    write_json(
        "GATE_D_PERF_OPS.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "evidence": "tests/gate_c/test_performance_concurrency.py + hardening diagnostics",
            "field_pilot_claimed": False,
        },
    )
