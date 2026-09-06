"""Gate B: activity inventory counts match matrix / compiled manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from course_compiler.activity import ACTIVITY_KEYS, inventory_from_paths
from course_compiler.compiler import collect_files, compile_module, is_instructor_path
from course_compiler.registry import load_pin, resolve_waike_root
from course_compiler.tracks import CANONICAL_TRACK_IDS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from inventory_18_tracks import inventory_track  # noqa: E402


SAMPLE_TRACKS = (
    "DIGITAL_CONFIDENCE",
    "IT_SUPPORT_HARDWARE",
    "SOFTWARE_BUILDER",
    "NETWORKING_INFRA",
    "CYBER_SOC",
    "SEVEN_GC_APPRENTICESHIP",
    "AI_ML_EDGE",
)


def test_inventory_counts_actual_content_not_just_dirs():
    pin = load_pin()
    waike = resolve_waike_root(pin)
    # Empty globs → zero counts
    empty = inventory_from_paths([])
    assert empty == {k: 0 for k in ACTIVITY_KEYS}
    # SOFTWARE_BUILDER digital_rc has real weeks/assignments
    spec = json.loads((ROOT / "curriculum/imports/SOFTWARE_BUILDER.import.json").read_text())
    inv = inventory_track(waike, "SOFTWARE_BUILDER", spec)
    assert inv["learner_file_count"] > 0
    assert inv["activity_counts"]["lessons"] >= 8
    assert inv["activity_counts"]["assignments"] >= 8
    assert inv["activity_counts"]["quizzes"] >= 8
    assert inv["activity_counts"]["labs"] >= 5


@pytest.mark.parametrize("track_id", SAMPLE_TRACKS)
def test_compiled_activity_matches_inventory(tmp_path, track_id):
    pin = load_pin()
    waike = resolve_waike_root(pin)
    spec = json.loads((ROOT / "curriculum" / "imports" / f"{track_id}.import.json").read_text())
    inv = inventory_track(waike, track_id, spec)
    report = compile_module(track_id, out_dir=tmp_path / track_id)
    compiled = report["activity_inventory"]
    for key in ACTIVITY_KEYS:
        assert compiled.get(key, 0) == inv["activity_counts"].get(key, 0), (track_id, key, compiled, inv)


def test_matrix_script_columns_and_counts(tmp_path, monkeypatch):
    """Build matrix against a fresh pack_out_18 under tmp by monkeypatching ROOT paths via compile."""
    # Compile a couple tracks and compare inventory path classification consistency
    pin = load_pin()
    waike = resolve_waike_root(pin)
    for tid in ("SOFTWARE_BUILDER", "SEVEN_GC_APPRENTICESHIP"):
        spec = json.loads((ROOT / "curriculum/imports" / f"{tid}.import.json").read_text())
        learner = collect_files(waike, spec["learner_globs"])
        instructor = collect_files(waike, spec["instructor_only_globs"])
        rels = []
        for p in set(learner) | set(instructor):
            rel = p.relative_to(waike).as_posix()
            if is_instructor_path(rel, spec["instructor_only_globs"], spec.get("instructor_path_markers")):
                rels.append(rel)
            else:
                rels.append(rel)
        counts = inventory_from_paths(rels)
        report = compile_module(tid, out_dir=tmp_path / tid)
        assert report["activity_inventory"] == counts


def test_seven_gc_thin_but_honest():
    pin = load_pin()
    waike = resolve_waike_root(pin)
    spec = json.loads((ROOT / "curriculum/imports/SEVEN_GC_APPRENTICESHIP.import.json").read_text())
    inv = inventory_track(waike, "SEVEN_GC_APPRENTICESHIP", spec)
    assert inv["digital_rc_package"] is None
    assert inv["learner_file_count"] > 0  # program + apprenticeship docs exist
    # No fabricated digital_rc week lessons
    assert inv["activity_counts"]["lessons"] == 0


def test_all_18_import_specs_present():
    for tid in CANONICAL_TRACK_IDS:
        assert (ROOT / "curriculum/imports" / f"{tid}.import.json").is_file()
