"""Learner pack + instructor *plaintext* are deterministic; AES-GCM ciphertext is not."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compiler import compile_module  # noqa: E402
from course_compiler.crypto import decrypt_aes_gcm, load_aes_key, sha256_file  # noqa: E402

KEYS = ROOT / "contracts" / "fixtures" / "keys"
AES = KEYS / "TEST_ONLY_instructor_aes256.key"


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


def test_instructor_plaintext_deterministic_ciphertext_unique(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = compile_module("DIGITAL_CONFIDENCE", out_dir=a)
    rb = compile_module("DIGITAL_CONFIDENCE", out_dir=b)
    assert ra["instructor_plaintext_sha256"] == rb["instructor_plaintext_sha256"]
    assert ra["instructor_manifest_sha256"] == rb["instructor_manifest_sha256"]

    ma = json.loads((a / "instructor_pack_manifest.json").read_text())
    mb = json.loads((b / "instructor_pack_manifest.json").read_text())
    na = base64.b64decode(ma["encryption"]["nonce_b64"])
    nb = base64.b64decode(mb["encryption"]["nonce_b64"])
    assert na != nb
    assert sha256_file(a / "DIGITAL_CONFIDENCE.instructor.aes256gcm") != sha256_file(
        b / "DIGITAL_CONFIDENCE.instructor.aes256gcm"
    )

    key = load_aes_key(AES)
    pa = decrypt_aes_gcm(key, na, (a / "DIGITAL_CONFIDENCE.instructor.aes256gcm").read_bytes())
    pb = decrypt_aes_gcm(key, nb, (b / "DIGITAL_CONFIDENCE.instructor.aes256gcm").read_bytes())
    assert pa == pb
    from course_compiler.crypto import sha256_bytes

    assert sha256_bytes(pa) == ra["instructor_plaintext_sha256"]
