"""All-18-track acceptance matrix for Gate D — consumes Gate B matrix_final_status."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gd_helpers import PINS, ROOT, write_json

MATRIX = ROOT / "reports" / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"
ACCEPT = ROOT / "reports" / "GATE_B_TRACK_ACCEPTANCE.json"
PIN = ROOT / "curriculum" / "registry" / "PIN.json"


def _matrix_row(matrix: dict, track_id: str) -> dict | None:
    rows = matrix.get("rows") or []
    return next((r for r in rows if r.get("track") == track_id or r.get("track_id") == track_id), None)


def test_all_18_tracks_digitally_available():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    assert pin["pinned_commit"] == PINS["waike"]
    allowed = pin["module_ids_allowed"]
    assert len(allowed) == 18
    assert len(set(allowed)) == 18

    assert MATRIX.is_file(), "compile-all / build_18_track_matrix must run first"
    assert ACCEPT.is_file(), "GATE_B_TRACK_ACCEPTANCE.json required (Gate B e2e matrix)"

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    acceptance = json.loads(ACCEPT.read_text(encoding="utf-8"))
    acc_rows = acceptance.get("tracks") or acceptance.get("rows") or []
    assert isinstance(acc_rows, list) and acc_rows, "Gate B acceptance tracks list missing/empty"

    by_track = {
        (r.get("track") or r.get("track_id")): r
        for r in acc_rows
        if (r.get("track") or r.get("track_id"))
    }

    out_rows = []
    for track_id in allowed:
        match = by_track.get(track_id)
        assert match is not None, f"track {track_id} missing from Gate B acceptance"
        final = match.get("matrix_final_status")
        assert final is not None and str(final).strip() != "", (
            f"track {track_id}: matrix_final_status missing/null"
        )

        mrow = _matrix_row(matrix, track_id) or {}
        dims = {
            "install": match.get("matrix_install") or mrow.get("install"),
            "learner_visible": match.get("matrix_learner_visible") or mrow.get("learner_visible"),
            "instructor_visible": match.get("matrix_instructor_visible")
            or mrow.get("instructor_visible"),
            "offline": match.get("matrix_offline") or mrow.get("offline"),
            "outcomes": mrow.get("outcome_coverage"),
            "rubrics": mrow.get("rubric_coverage"),
        }
        # Document NO/N/A truthfully — never rewrite NO → PASS.
        honest_dims = {
            k: ("N/A" if v in (None, "", "NOT_APPLICABLE") else str(v)) for k, v in dims.items()
        }

        e2e = match.get("e2e") or {}
        activity = match.get("activity_counts") or {}
        representative = (
            int(activity.get("lessons") or 0)
            + int(activity.get("assignments") or 0)
            + int(activity.get("labs") or 0)
            + int(activity.get("quizzes") or 0)
        )
        # Real activity evidence from Gate B acceptance — not package-directory counts alone.
        activity_ok = representative > 0 and e2e.get("learner") == "PASS" and e2e.get("install") == "PASS"

        status = "PASS" if final == "PASS" and activity_ok else "FAIL"
        if final not in ("PASS", "BLOCKED", "EXTERNAL_PHYSICAL_GATE", "NO", "FAIL"):
            status = "FAIL"

        out_rows.append(
            {
                "track_id": track_id,
                "stable_id": track_id,
                "matrix_final_status": final,
                "dimensions": honest_dims,
                "activity_counts": activity,
                "e2e": e2e,
                "representative_activity_ok": activity_ok,
                "status": status,
                "blocker": match.get("blocker") or "",
            }
        )

    failed = [r for r in out_rows if r["status"] != "PASS"]
    data = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "waike_pin": PINS["waike"],
        "track_count": len(out_rows),
        "rows": out_rows,
        "all_pass": len(failed) == 0 and len(out_rows) == 18,
        "method": "gate_b_matrix_final_status_plus_e2e_activity_not_registry_auto_pass",
        "dimension_honesty": (
            "NO/N/A dimensions recorded as-is; digital availability uses matrix_final_status "
            "PASS + representative e2e/activity proof, without stamping PASS over NO."
        ),
    }
    write_json("GATE_D_ALL_18_TRACK_ACCEPTANCE.json", data)
    lines = [
        "# Gate D All-18 Track Acceptance",
        "",
        f"Generated: {data['generated_utc']}",
        "",
        f"Tracks: **{data['track_count']}** | all_pass: **{data['all_pass']}**",
        "",
        "| track_id | matrix_final | offline | outcomes | rubrics | status |",
        "|----------|--------------|---------|----------|---------|--------|",
    ]
    for r in out_rows:
        d = r["dimensions"]
        lines.append(
            f"| `{r['track_id']}` | `{r['matrix_final_status']}` | `{d.get('offline')}` | "
            f"`{d.get('outcomes')}` | `{d.get('rubrics')}` | `{r['status']}` |"
        )
    (ROOT / "reports" / "GATE_D_ALL_18_TRACK_ACCEPTANCE.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    assert data["all_pass"] is True
    assert data["track_count"] == 18
