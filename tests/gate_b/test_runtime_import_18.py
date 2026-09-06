"""Package → runtime registration proofs (Gate B B6 / runtime-import-18)."""

from __future__ import annotations

from course_compiler.tracks import CANONICAL_TRACK_IDS
from helpers import (
    activity_counts_from_pack,
    install_track_into_hub,
    resolve_pack_dir,
)


def test_runtime_import_registers_pack_module_ids(client, packs_18):
    """Every imported activity must carry the installed track's module_id."""
    sample = [
        tid
        for tid in CANONICAL_TRACK_IDS
        if tid != "SEVEN_GC_APPRENTICESHIP"
        and sum(activity_counts_from_pack(resolve_pack_dir(tid, packs_18)).values()) > 0
    ][:3]
    assert sample, "expected at least one non-shell track with pack activities"

    for track_id in sample:
        pack_dir = resolve_pack_dir(track_id, packs_18)
        installed = install_track_into_hub(client, track_id, pack_dir)
        registered = installed.get("registered_activities") or {}
        assert registered.get("module_id") == track_id
        for key in ("assignment", "quiz", "lab"):
            row = registered.get(key)
            if not row:
                continue
            assert row.get("module_id") == track_id, (track_id, key, row)


def test_runtime_import_seven_gc_shell_is_not_applicable(client, packs_18):
    track_id = "SEVEN_GC_APPRENTICESHIP"
    pack_dir = resolve_pack_dir(track_id, packs_18)
    counts = activity_counts_from_pack(pack_dir)
    assert counts["lessons"] == 0
    assert counts["assignments"] == 0
    assert counts["quizzes"] == 0
    assert counts["labs"] == 0
    installed = install_track_into_hub(client, track_id, pack_dir)
    registered = installed.get("registered_activities") or {}
    status = registered.get("status") or {}
    assert status.get("assignments") == "NOT_APPLICABLE"
    assert status.get("quizzes") == "NOT_APPLICABLE"
    assert status.get("labs") == "NOT_APPLICABLE"
    assert registered.get("assignment") is None
    assert registered.get("quiz") is None
    assert registered.get("lab") is None
