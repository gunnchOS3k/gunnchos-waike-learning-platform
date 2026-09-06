"""Gate B aggregator: track acceptance statuses consistent with compile matrix."""

from __future__ import annotations

import json
from pathlib import Path

from course_compiler.tracks import CANONICAL_TRACK_IDS
from course_compiler.verify import open_instructor_pack, verify_learner_pack
from helpers import AES, MATRIX_PATH, ROOT, VK, load_matrix, resolve_pack_dir

ACCEPTANCE_PATH = ROOT / "reports" / "GATE_B_TRACK_ACCEPTANCE.json"


def test_matrix_has_all_18_tracks():
    data = load_matrix()
    tracks = {r["track"] for r in data["rows"]}
    assert tracks == set(CANONICAL_TRACK_IDS)


def test_matrix_final_status_matches_compile_results(packs_18):
    data = load_matrix()
    by_track = {r["track"]: r for r in data["rows"]}
    inconsistencies: list[str] = []

    for track_id in CANONICAL_TRACK_IDS:
        row = by_track[track_id]
        pack_dir = resolve_pack_dir(track_id, packs_18)
        decision = verify_learner_pack(pack_dir, VK)
        dec = open_instructor_pack(pack_dir, AES)

        verify_ok = decision.ok
        decrypt_ok = bool(getattr(dec, "ok", False))
        expected_final = "PASS" if verify_ok and decrypt_ok else "FAIL"

        if row.get("verification") == "PASS" and not verify_ok:
            inconsistencies.append(f"{track_id}: matrix verification PASS but pack verify failed")
        if str(row.get("decrypt", "")).startswith("PASS") and not decrypt_ok:
            inconsistencies.append(f"{track_id}: matrix decrypt PASS but open_instructor failed")
        if row.get("final_status") != expected_final:
            # Thin SEVEN_GC may still PASS compile with EMPTY instructor files
            if not (
                track_id == "SEVEN_GC_APPRENTICESHIP"
                and row.get("final_status") == "PASS"
                and verify_ok
                and decrypt_ok
            ):
                inconsistencies.append(
                    f"{track_id}: final_status={row.get('final_status')} expected={expected_final}"
                )

        if row.get("install") == "PASS":
            assert verify_ok, track_id
        if row.get("learner_visible") == "PASS":
            assert verify_ok, track_id

    assert not inconsistencies, inconsistencies


def test_acceptance_skeleton_populated_from_matrix(packs_18):
    data = load_matrix()
    tracks = []
    for row in data["rows"]:
        track_id = row["track"]
        pack_dir = resolve_pack_dir(track_id, packs_18)
        decision = verify_learner_pack(pack_dir, VK)
        tracks.append(
            {
                "track": track_id,
                "matrix_final_status": row.get("final_status"),
                "matrix_install": row.get("install"),
                "matrix_learner_visible": row.get("learner_visible"),
                "matrix_instructor_visible": row.get("instructor_visible"),
                "matrix_offline": row.get("offline"),
                "compile_verify_ok": decision.ok,
                "activity_counts": {
                    "lessons": row.get("lessons", 0),
                    "assignments": row.get("assignments", 0),
                    "quizzes": row.get("quizzes", 0),
                    "labs": row.get("labs", 0),
                    "rubrics": row.get("rubrics", 0),
                },
                "e2e": {
                    "install": "PENDING_SUITE",
                    "learner": "PENDING_SUITE",
                    "instructor": "PENDING_SUITE",
                    "offline": "PENDING_SUITE",
                },
                "blocker": row.get("blocker") or "",
            }
        )

    payload = {
        "schema": "waike.gate_b.track_acceptance.v1",
        "source_matrix": str(MATRIX_PATH.relative_to(ROOT)),
        "tracks": tracks,
        "summary": {
            "track_count": len(tracks),
            "matrix_pass": sum(1 for t in tracks if t["matrix_final_status"] == "PASS"),
            "matrix_fail": sum(1 for t in tracks if t["matrix_final_status"] != "PASS"),
        },
        "notes": [
            "Skeleton populated from WAIKE_18_TRACK_PACKAGE_MATRIX.json.",
            "E2E suite statuses are asserted live by test_install/learner/instructor/offline_18.",
            "SEVEN_GC_APPRENTICESHIP may be thin (zero digital_rc weeks) without inventing content.",
        ],
    }
    ACCEPTANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCEPTANCE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    assert ACCEPTANCE_PATH.is_file()
    assert payload["summary"]["track_count"] == 18
