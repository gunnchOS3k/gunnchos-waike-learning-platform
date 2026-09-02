"""Compatibility policy typed rejection reasons."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compat import (  # noqa: E402
    DEFAULT_COMPAT,
    RejectionReason,
    check_compatibility_manifest,
)


def test_default_compat_ok():
    d = check_compatibility_manifest(DEFAULT_COMPAT)
    assert d.ok


def test_platform_too_old():
    m = dict(DEFAULT_COMPAT)
    m["platform_min"] = "9.0.0"
    d = check_compatibility_manifest(m, platform_version="0.1.0")
    assert not d.ok
    assert d.reason == RejectionReason.PLATFORM_TOO_OLD
    assert d.to_dict()["ui_code"] == "PLATFORM_TOO_OLD"


def test_incompatible_contract_major():
    m = dict(DEFAULT_COMPAT)
    m["contracts"] = {**m["contracts"], "learner_pack_manifest": {"major": 99, "min_minor": 0}}
    d = check_compatibility_manifest(m)
    assert not d.ok
    assert d.reason == RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR
