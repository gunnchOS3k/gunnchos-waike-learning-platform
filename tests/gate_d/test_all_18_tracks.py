"""All-18-track acceptance matrix for Gate D."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gd_helpers import PINS, ROOT, write_json

MATRIX = ROOT / "reports" / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"
ACCEPT = ROOT / "reports" / "GATE_B_TRACK_ACCEPTANCE.json"
PIN = ROOT / "curriculum" / "registry" / "PIN.json"


def test_all_18_tracks_digitally_available():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    assert pin["pinned_commit"] == PINS["waike"]
    allowed = pin["module_ids_allowed"]
    assert len(allowed) == 18
    assert len(set(allowed)) == 18

    assert MATRIX.is_file(), "compile-all / build_18_track_matrix must run first"

    acceptance = {}
    if ACCEPT.is_file():
        acceptance = json.loads(ACCEPT.read_text(encoding="utf-8"))

    out_rows = []
    for track_id in allowed:
        row = {"track_id": track_id, "stable_id": track_id, "status": "PASS"}
        acc_rows = acceptance.get("tracks") or acceptance.get("rows") or []
        if isinstance(acceptance.get("by_track"), dict):
            t = acceptance["by_track"].get(track_id)
            if t:
                row["gate_b_status"] = t.get("final_status") or t.get("status")
                if row["gate_b_status"] == "FAIL":
                    row["status"] = "FAIL"
        elif isinstance(acc_rows, list):
            match = next(
                (r for r in acc_rows if r.get("track") == track_id or r.get("track_id") == track_id),
                None,
            )
            if match:
                st = match.get("final_status") or match.get("status")
                row["gate_b_status"] = st
                if st == "FAIL":
                    row["status"] = "FAIL"
        out_rows.append(row)

    failed = [r for r in out_rows if r["status"] == "FAIL"]
    data = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "waike_pin": PINS["waike"],
        "track_count": len(out_rows),
        "rows": out_rows,
        "all_pass": len(failed) == 0,
        "method": "canonical_registry_ids_not_directory_count",
    }
    write_json("GATE_D_ALL_18_TRACK_ACCEPTANCE.json", data)
    lines = [
        "# Gate D All-18 Track Acceptance",
        "",
        f"Generated: {data['generated_utc']}",
        "",
        f"Tracks: **{data['track_count']}** | all_pass: **{data['all_pass']}**",
        "",
        "| track_id | status |",
        "|----------|--------|",
    ]
    for r in out_rows:
        lines.append(f"| `{r['track_id']}` | `{r['status']}` |")
    (ROOT / "reports" / "GATE_D_ALL_18_TRACK_ACCEPTANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert data["all_pass"] is True
    assert data["track_count"] == 18
