"""TEST_ONLY keys must never masquerade as production signing material."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compat import RejectionReason  # noqa: E402
from course_compiler.registry import RegistryError, assert_signing_key_allowed  # noqa: E402

KEYS = ROOT / "contracts" / "fixtures" / "keys"


def test_test_only_key_allowed_in_dev():
    assert_signing_key_allowed(KEYS / "TEST_ONLY_ed25519_private.key", release_mode=False)


def test_test_only_key_forbidden_in_release():
    with pytest.raises(RegistryError) as exc:
        assert_signing_key_allowed(KEYS / "TEST_ONLY_ed25519_private.key", release_mode=True)
    assert exc.value.reason == RejectionReason.RELEASE_TEST_KEY_FORBIDDEN


def test_unlabeled_key_forbidden_even_in_dev(tmp_path: Path):
    unlabeled = tmp_path / "ed25519_private.key"
    unlabeled.write_bytes((KEYS / "TEST_ONLY_ed25519_private.key").read_bytes())
    with pytest.raises(RegistryError) as exc:
        assert_signing_key_allowed(unlabeled, release_mode=False)
    assert exc.value.reason == RejectionReason.RELEASE_TEST_KEY_FORBIDDEN


def test_learner_pack_contains_no_private_keys(tmp_path: Path):
    from course_compiler.compiler import compile_module

    out = tmp_path / "build"
    compile_module("DIGITAL_CONFIDENCE", out_dir=out)
    for p in (out / "learner").rglob("*"):
        if not p.is_file():
            continue
        low = p.name.lower()
        assert "private" not in low
        assert not low.endswith(".pem")
        assert not low.endswith(".key")
        assert "test_only_ed25519_private" not in low
