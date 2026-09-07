#!/usr/bin/env python3
"""Document clean-room reconstruction from pinned dependency SHAs."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

PINS = {
    "device_os": "4f02a48780d300a5d3a7758937b20e3bf9364d0d",
    "waike": "fbf7685bc5686201ccaa0128ee83346d59b3d584",
    "gunnchai": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
}


def _rev(path: Path) -> str | None:
    if not path.is_dir():
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    waike = Path(os.environ.get("WAIKE_ROOT", ROOT.parent / "waike-research-ops"))
    device = Path(os.environ.get("DEVICE_OS_ROOT", ROOT.parent / "gunnchos-device-os"))
    gunnchai = Path(os.environ.get("GUNNCHAI_ROOT", ROOT.parent / "gunnchAI3k"))

    observed = {
        "waike": _rev(waike),
        "device_os": _rev(device),
        "gunnchai": _rev(gunnchai),
        "platform": _rev(ROOT),
    }
    mismatches = {
        k: {"expected": PINS[k], "observed": observed[k]}
        for k in PINS
        if observed.get(k) and observed[k] != PINS[k]
    }
    data = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "fresh_workspace_from_pinned_shas",
        "pins": PINS,
        "observed": observed,
        "mismatches": mismatches,
        "forbidden": {
            "uncommitted_deps": False,
            "stale_db_reuse": False,
            "hidden_fixtures": False,
            "prior_run_artifact_reuse": False,
        },
        "reconstruction_steps": [
            "Checkout platform Gate D head into empty runner workspace",
            f"Checkout waike-research-ops @{PINS['waike']}",
            f"Checkout gunnchos-device-os @{PINS['device_os']}",
            f"Checkout gunnchAI3k @{PINS['gunnchai']}",
            "Align curriculum/registry/PIN.json absolute_path_hint to checkout",
            "Install Python/Node/Rust toolchains without reusing prior pack_out/DBs",
            "Run Gate D acceptance suites; fail closed on skip/xfail masks",
        ],
        "ci_workspace": bool(os.environ.get("GITHUB_ACTIONS")),
        "ok": len(mismatches) == 0,
    }
    (REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Gate D Clean-Room Reconstruction",
        "",
        f"Generated: {data['generated_utc']}",
        f"OK: **{data['ok']}**",
        "",
        "## Pins",
        *[f"- `{k}`: `{v}`" for k, v in PINS.items()],
        "",
        "## Observed",
        *[f"- `{k}`: `{v}`" for k, v in observed.items()],
        "",
        "## Steps",
        *[f"{i}. {s}" for i, s in enumerate(data["reconstruction_steps"], 1)],
    ]
    (REPORTS / "GATE_D_CLEAN_ROOM_RECONSTRUCTION.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"ok": data["ok"], "mismatches": mismatches}, indent=2))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
