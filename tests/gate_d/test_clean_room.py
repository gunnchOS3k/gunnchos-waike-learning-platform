"""Clean-room reconstruction checks for Gate D."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from gd_helpers import PINS, ROOT

REPORTS = ROOT / "reports"


def test_clean_room_pins_and_measured_forbidden():
    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text(encoding="utf-8"))
    assert pin["pinned_commit"] == PINS["waike"]

    wf = (ROOT / ".github/workflows/gate-d.yml").read_text(encoding="utf-8")
    assert f'DEVICE_OS_PIN_REF: "{PINS["device_os"]}"' in wf
    assert f'WAIKE_PIN_REF: "{PINS["waike"]}"' in wf
    assert f'GUNNCHAI_PIN_REF: "{PINS["gunnchai"]}"' in wf

    job_body = "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))
    assert "continue-on-error: true" not in job_body
    assert re.search(r"\|\|\s*true", job_body) is None

    # Measured reconstruction (no hardcoded forbidden:false constants in script source).
    src = (ROOT / "scripts/clean_room_reconstruct.py").read_text(encoding="utf-8")
    assert "fixture_only_production_proof" in src
    assert '"uncommitted_deps": False' not in src
    assert "hidden_fixtures" not in src or "fixture_only_production_proof" in src

    env = os.environ.copy()
    env.setdefault("WAIKE_ROOT", str(ROOT.parent / "waike-research-ops"))
    env.setdefault("DEVICE_OS_ROOT", str(ROOT.parent / "gunnchos-device-os"))
    env.setdefault("GUNNCHAI_ROOT", str(ROOT.parent / "gunnchAI3k"))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/clean_room_reconstruct.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    recon = REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.json"
    assert recon.is_file(), proc.stdout + proc.stderr
    data = json.loads(recon.read_text(encoding="utf-8"))
    assert data["pins"]["waike"] == PINS["waike"]
    assert data["pins"]["device_os"] == PINS["device_os"]
    assert data["pins"]["gunnchai"] == PINS["gunnchai"]
    assert "measurements" in data
    assert "fixture_only_production_proof" in data["forbidden"]
    assert "hidden_fixtures" not in data["forbidden"]
    # In CI the measured reconstruction must be ok; locally pin checkouts may be dirty.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        assert proc.returncode == 0
        assert data["ok"] is True
        assert data["forbidden"]["uncommitted_deps"] is False
        assert data["forbidden"]["stale_db_reuse"] is False
        assert data["forbidden"]["prior_run_artifact_reuse"] is False
        assert data["forbidden"]["fixture_only_production_proof"] is False
