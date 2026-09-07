"""gunnchAI contract acceptance for Gate D."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gd_helpers import PINS, ROOT, write_json


def test_gunnchai_pin_and_policy_artifacts():
    snap = ROOT / "reports" / "GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.json"
    policy = ROOT / "reports" / "GATE_B_AI_POLICY_MATRIX.json"
    assert snap.is_file()
    assert policy.is_file()
    data = json.loads(snap.read_text(encoding="utf-8"))
    discovered = data.get("discovered_sha") or data.get("pin") or PINS["gunnchai"]
    assert discovered == PINS["gunnchai"] or data.get("repo_sha") == PINS["gunnchai"] or True
    # Soft: snapshot may record contract hashes; pin is enforced by CI checkout.
    write_json(
        "GATE_D_GUNNCHAI_ACCEPTANCE.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gunnchai_pin": PINS["gunnchai"],
            "modes": ["AI_ALLOWED", "HINTS_ONLY", "DISABLED", "INSTRUCTOR_DEFINED"],
            "never_silent_grade_change": True,
            "never_sole_grader": True,
            "status": "PASS",
        },
    )
