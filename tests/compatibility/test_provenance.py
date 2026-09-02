"""Provenance gate: PIN declared commit must match observed WAIKE HEAD."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compiler import compile_module  # noqa: E402
from course_compiler.compat import RejectionReason  # noqa: E402
from course_compiler.registry import RegistryError, load_pin, verify_waike_provenance  # noqa: E402


def test_provenance_match_passes():
    pin = load_pin()
    result = verify_waike_provenance(pin)
    assert result["declared_pinned_commit"] == result["observed_source_commit"]
    assert result["declared_pinned_commit"] == pin["pinned_commit"]


def test_compile_aborts_on_pin_mismatch(tmp_path: Path, monkeypatch):
    """Leave PIN untouched on disk semantics: override loaded pin commit only."""
    pin = load_pin()
    bad = dict(pin)
    bad["pinned_commit"] = "0" * 40

    def _bad_pin(path=None):
        return bad

    monkeypatch.setattr("course_compiler.compiler.load_pin", _bad_pin)
    monkeypatch.setattr("course_compiler.registry.load_pin", _bad_pin)
    with pytest.raises(RegistryError) as exc:
        compile_module("DIGITAL_CONFIDENCE", out_dir=tmp_path / "should_not_exist")
    assert exc.value.reason == RejectionReason.PROVENANCE_MISMATCH
    assert not (tmp_path / "should_not_exist" / "DIGITAL_CONFIDENCE.learner.zip").exists()


def test_import_report_fields(tmp_path: Path):
    report = compile_module("DIGITAL_CONFIDENCE", out_dir=tmp_path / "ok")
    assert report["declared_pinned_commit"] == report["observed_source_commit"]
    assert report["provenance_match"] is True
    on_disk = json.loads((ROOT / "reports" / "DIGITAL_CONFIDENCE_IMPORT_REPORT.json").read_text())
    assert on_disk["declared_pinned_commit"] == on_disk["observed_source_commit"]
