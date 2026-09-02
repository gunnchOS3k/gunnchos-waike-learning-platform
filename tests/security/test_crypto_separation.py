"""Ten crypto separation / supply-chain negative tests (must all pass)."""

from __future__ import annotations

import base64
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler import crypto  # noqa: E402
from course_compiler.compiler import compile_module  # noqa: E402
from course_compiler.compat import RejectionReason, check_schema_version  # noqa: E402
from course_compiler.jsonutil import dumps_canonical  # noqa: E402
from course_compiler.verify import open_instructor_pack, verify_learner_pack  # noqa: E402

KEYS = ROOT / "contracts" / "fixtures" / "keys"
VK = KEYS / "TEST_ONLY_ed25519_public.key"
SK = KEYS / "TEST_ONLY_ed25519_private.key"
AES = KEYS / "TEST_ONLY_instructor_aes256.key"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("dc_build")
    report = compile_module("DIGITAL_CONFIDENCE", out_dir=out)
    return out, report


def _clone(built, tmp_path, name: str) -> Path:
    out, _ = built
    dest = tmp_path / name
    shutil.copytree(out, dest)
    return dest


def test_01_tampered_content_rejected(built, tmp_path):
    copy = _clone(built, tmp_path, "tampered")
    target = next(p for p in (copy / "learner").rglob("*.md") if p.is_file())
    data = bytearray(target.read_bytes())
    data[0] = (data[0] + 1) % 256
    target.write_bytes(bytes(data))
    decision = verify_learner_pack(copy, VK)
    assert not decision.ok
    assert decision.reason == RejectionReason.TAMPERED_CONTENT


def test_02_unsigned_pack_rejected(built, tmp_path):
    copy = _clone(built, tmp_path, "unsigned")
    (copy / "learner_pack.signature.json").unlink()
    decision = verify_learner_pack(copy, VK)
    assert not decision.ok
    assert decision.reason in (RejectionReason.UNSIGNED_PACK, RejectionReason.MISSING_SIGNATURE)


def test_03_wrong_role_rejected(built, tmp_path):
    copy = _clone(built, tmp_path, "wrong_role")
    manifest = json.loads((copy / "learner_pack_manifest.json").read_text())
    manifest["role"] = "instructor"
    sk = crypto.load_signing_key(SK)
    payload, meta = crypto.sign_manifest_dict(sk, manifest)
    (copy / "learner_pack_manifest.json").write_text(dumps_canonical(manifest))
    (copy / "learner_pack.manifest.canonical.json").write_bytes(payload)
    (copy / "learner_pack.signature.json").write_text(dumps_canonical(meta))
    decision = verify_learner_pack(copy, VK)
    assert not decision.ok
    assert decision.reason == RejectionReason.WRONG_ROLE


def test_04_incompatible_schema_major_rejected():
    d = check_schema_version("learner_pack_manifest", "2.0.0")
    assert not d.ok
    assert d.reason == RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR


def test_05_schema_downgrade_rejected():
    d = check_schema_version("learner_pack_manifest", "0.9.0")
    assert not d.ok
    assert d.reason in (RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR, RejectionReason.SCHEMA_DOWNGRADE)


def test_06_no_answer_keys_in_learner(built):
    out, _ = built
    decision = verify_learner_pack(out, VK)
    assert decision.ok
    for p in (out / "learner").rglob("*"):
        if not p.is_file():
            continue
        low = p.as_posix().lower()
        assert "answer_key" not in low
        assert "instructor_solution" not in low
        assert not low.endswith("teaching_notes.md")
        assert not low.endswith("demo_plan.md")


def test_07_no_private_keys_in_learner(built):
    out, _ = built
    for p in (out / "learner").rglob("*"):
        if not p.is_file():
            continue
        low = p.name.lower()
        assert "private" not in low
        assert not low.endswith(".pem")
        assert not low.endswith(".key")


def test_08_instructor_needs_correct_key(built):
    out, _ = built
    enc = out / "DIGITAL_CONFIDENCE.instructor.aes256gcm"
    man = out / "instructor_pack_manifest.json"
    plain = open_instructor_pack(enc, man, AES.read_bytes())
    assert len(plain) > 0
    with pytest.raises(ValueError):
        open_instructor_pack(enc, man, b"\x00" * 32)


def test_09_one_bit_corruption_rejected(built, tmp_path):
    copy = _clone(built, tmp_path, "onebit")
    sig = json.loads((copy / "learner_pack.signature.json").read_text())
    raw = bytearray(base64.b64decode(sig["signature_b64"]))
    raw[0] ^= 0x01
    sig["signature_b64"] = base64.b64encode(bytes(raw)).decode("ascii")
    (copy / "learner_pack.signature.json").write_text(dumps_canonical(sig))
    decision = verify_learner_pack(copy, VK)
    assert not decision.ok
    assert decision.reason in (RejectionReason.BAD_SIGNATURE, RejectionReason.ONE_BIT_CORRUPTION)


def test_10_verify_before_trust(built, tmp_path):
    copy = _clone(built, tmp_path, "vbt")
    ok = verify_learner_pack(copy, VK)
    assert ok.ok
    (copy / "learner_pack.signature.json").unlink()
    bad = verify_learner_pack(copy, VK)
    assert not bad.ok
    assert bad.reason in (
        RejectionReason.UNSIGNED_PACK,
        RejectionReason.MISSING_SIGNATURE,
        RejectionReason.VERIFY_BEFORE_TRUST,
    )
