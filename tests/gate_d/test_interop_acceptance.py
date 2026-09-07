"""Interop acceptance — implemented subsets only; no certification claims."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gd_helpers import ROOT, write_json


def test_interop_matrices_present_and_honest():
    required = (
        "GATE_C_ONEROSTER_MATRIX.json",
        "GATE_C_QTI_MATRIX.json",
        "GATE_C_LTI_MATRIX.json",
    )
    for name in required:
        path = ROOT / "reports" / name
        assert path.is_file(), f"missing interop matrix: {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data, f"empty interop matrix: {name}"
        # Never claim external certification from Gate D digital suites.
        assert data.get("certification_claimed") is not True
        assert data.get("externally_certified") is not True

    write_json(
        "GATE_D_INTEROP_ACCEPTANCE.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "certification_claimed": False,
            "subsets": ["OneRoster", "QTI", "LTI"],
            "adversarial_rejection": "exercised_via_gate_c_security_suites",
        },
    )
