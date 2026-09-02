"""Learner pack must be byte-identical under fixed SOURCE_DATE_EPOCH + test keys."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compiler import compile_module  # noqa: E402
from course_compiler.crypto import sha256_file  # noqa: E402


@pytest.fixture(autouse=True)
def _epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def test_learner_pack_byte_identical(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = compile_module("DIGITAL_CONFIDENCE", out_dir=a)
    rb = compile_module("DIGITAL_CONFIDENCE", out_dir=b)
    za = a / "DIGITAL_CONFIDENCE.learner.zip"
    zb = b / "DIGITAL_CONFIDENCE.learner.zip"
    assert za.exists() and zb.exists()
    ha, hb = sha256_file(za), sha256_file(zb)
    assert ha == hb == ra["learner_zip_sha256"] == rb["learner_zip_sha256"]
    # Instructor ciphertext also deterministic under SOURCE_DATE_EPOCH
    ia = a / "DIGITAL_CONFIDENCE.instructor.aes256gcm"
    ib = b / "DIGITAL_CONFIDENCE.instructor.aes256gcm"
    assert sha256_file(ia) == sha256_file(ib)
