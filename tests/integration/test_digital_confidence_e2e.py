"""End-to-end-ish: compile, verify, install service layer, resume position."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.compiler import compile_module  # noqa: E402
from course_compiler.registry import resolve_module_id  # noqa: E402
from course_compiler.verify import verify_learner_pack  # noqa: E402

KEYS = ROOT / "contracts" / "fixtures" / "keys"
VK = KEYS / "TEST_ONLY_ed25519_public.key"


def test_fail_closed_unknown_module():
    import pytest
    from course_compiler.registry import RegistryError

    with pytest.raises(RegistryError):
        resolve_module_id("NOT_A_REAL_MODULE")


def test_compile_install_resume(tmp_path):
    out = tmp_path / "build"
    report = compile_module("DIGITAL_CONFIDENCE", out_dir=out)
    assert report["learner_file_count"] > 10
    assert report["instructor_file_count"] > 0
    assert len(report["lessons"]) >= 8

    decision = verify_learner_pack(out, VK)
    assert decision.ok

    # Simulated install + encrypted position store (Python stand-in for Rust layer)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    # copy verified learner tree
    import shutil

    shutil.copytree(out / "learner", install_dir / "content")
    shutil.copy2(out / "learner_pack_manifest.json", install_dir / "learner_pack_manifest.json")
    shutil.copy2(out / "learner_pack.signature.json", install_dir / "learner_pack.signature.json")

    lesson = report["lessons"][0]
    position = {"module_id": "DIGITAL_CONFIDENCE", "lesson_id": lesson["lesson_id"], "offset": 42}
    key = os.urandom(32)
    nonce = os.urandom(12)
    blob = AESGCM(key).encrypt(nonce, json.dumps(position).encode(), None)
    db_path = install_dir / "progress.db.enc"
    db_path.write_bytes(nonce + blob)

    # restart simulation
    raw = db_path.read_bytes()
    resumed = json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None))
    assert resumed["lesson_id"] == lesson["lesson_id"]
    assert resumed["offset"] == 42

    # no instructor material in learner content
    for p in (install_dir / "content").rglob("*"):
        if p.is_file():
            low = p.as_posix().lower()
            assert "instructor_solution" not in low
            assert "answer_key" not in low
