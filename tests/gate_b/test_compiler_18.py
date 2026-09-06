"""Gate B: compile all 18 tracks, verify learner packs, decrypt instructor, no leaks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_compiler.compiler import compile_all, compile_module
from course_compiler.registry import load_pin, resolve_module_id
from course_compiler.tracks import CANONICAL_TRACK_IDS
from course_compiler.verify import open_instructor_pack, verify_learner_pack

ROOT = Path(__file__).resolve().parents[2]
KEYS = ROOT / "contracts" / "fixtures" / "keys"
VK = KEYS / "TEST_ONLY_ed25519_public.key"
AES = KEYS / "TEST_ONLY_instructor_aes256.key"


@pytest.fixture(scope="module")
def compiled_18(tmp_path_factory):
    out = tmp_path_factory.mktemp("pack_out_18")
    results = compile_all(tracks=list(CANONICAL_TRACK_IDS), out_root=out)
    return out, results


def test_pin_allows_all_18():
    pin = load_pin()
    allowed = set(pin["module_ids_allowed"])
    assert allowed == set(CANONICAL_TRACK_IDS)
    assert pin["pinned_commit"] == "fbf7685bc5686201ccaa0128ee83346d59b3d584"
    assert pin.get("seven_gc_digital_merge_commit") == pin["pinned_commit"]


def test_aliases_map_package_ids():
    pin = load_pin()
    assert resolve_module_id("COMPUTER_NETWORKING", pin) == "NETWORKING_INFRA"
    assert resolve_module_id("CYBERSECURITY", pin) == "CYBER_SOC"
    assert resolve_module_id("WAIKE_COURSE_SOFTWARE_BUILDER", pin) == "SOFTWARE_BUILDER"


def test_compile_all_18_ok(compiled_18):
    out, results = compiled_18
    assert results["ok"] is True, results.get("failures")
    assert set(results["tracks"]) == set(CANONICAL_TRACK_IDS)
    for tid in CANONICAL_TRACK_IDS:
        assert results["tracks"][tid]["ok"] is True, tid
        assert (out / tid / f"{tid}.learner.zip").is_file()
        assert (out / tid / f"{tid}.instructor.aes256gcm").is_file()


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_verify_and_decrypt_per_track(compiled_18, track_id):
    out, _ = compiled_18
    pack = out / track_id
    decision = verify_learner_pack(pack, VK)
    assert decision.ok, (track_id, decision.to_dict())
    dec = open_instructor_pack(pack, AES)
    assert dec.ok, (track_id, dec.to_dict())


@pytest.mark.parametrize("track_id", CANONICAL_TRACK_IDS)
def test_no_instructor_leak_into_learner(compiled_18, track_id):
    out, _ = compiled_18
    man = json.loads((out / track_id / "learner_pack_manifest.json").read_text(encoding="utf-8"))
    for entry in man.get("files") or []:
        low = entry["path"].lower()
        assert "/instructor/" not in low, entry["path"]
        assert "answer_key" not in low, entry["path"]
        assert not low.endswith("teaching_notes.md"), entry["path"]
        assert not low.endswith("demo_plan.md"), entry["path"]
        assert "answer_keys.json" not in low, entry["path"]


def test_digital_confidence_still_compiles(tmp_path):
    report = compile_module("DIGITAL_CONFIDENCE", out_dir=tmp_path / "dc")
    assert report["module_id"] == "DIGITAL_CONFIDENCE"
    assert report["provenance_match"] is True
    assert len(report["lessons"]) >= 8
    decision = verify_learner_pack(tmp_path / "dc", VK)
    assert decision.ok
