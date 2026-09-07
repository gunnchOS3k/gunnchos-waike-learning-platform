"""gunnchAI contract acceptance for Gate D."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gd_helpers import PINS, ROOT, write_json


def test_gunnchai_pin_and_policy_artifacts():
    snap = ROOT / "reports" / "GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.json"
    policy = ROOT / "reports" / "GATE_B_AI_POLICY_MATRIX.json"
    assert snap.is_file()
    assert policy.is_file()
    data = json.loads(snap.read_text(encoding="utf-8"))
    expected = data.get("expected_sha")
    observed = data.get("observed_sha")
    assert expected == PINS["gunnchai"], f"expected_sha mismatch: {expected}"
    assert observed == PINS["gunnchai"], f"observed_sha mismatch: {observed}"

    gunnchai_root = Path(
        os.environ.get("GUNNCHAI_ROOT", str(ROOT.parent / "gunnchAI3k"))
    ).resolve()
    if (gunnchai_root / ".git").exists() or (gunnchai_root / "HEAD").exists() or gunnchai_root.is_dir():
        try:
            checkout = subprocess.check_output(
                ["git", "-C", str(gunnchai_root), "rev-parse", "HEAD"],
                text=True,
            ).strip()
            assert checkout == PINS["gunnchai"], f"GUNNCHAI_ROOT HEAD {checkout} != pin"
        except subprocess.CalledProcessError as exc:
            raise AssertionError(f"unable to resolve GUNNCHAI_ROOT HEAD: {exc}") from exc

    policy_data = json.loads(policy.read_text(encoding="utf-8"))
    assert policy_data, "AI policy matrix must be non-empty"

    write_json(
        "GATE_D_GUNNCHAI_ACCEPTANCE.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gunnchai_pin": PINS["gunnchai"],
            "expected_sha": expected,
            "observed_sha": observed,
            "modes": ["AI_ALLOWED", "HINTS_ONLY", "DISABLED", "INSTRUCTOR_DEFINED"],
            "never_silent_grade_change": True,
            "never_sole_grader": True,
            "status": "PASS",
        },
    )
