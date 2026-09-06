"""Gate B: package security — signature verify, AES decrypt, path containment."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from course_compiler.compiler import compile_module
from course_compiler.crypto import b64d, decrypt_aes_gcm, load_aes_key, load_verify_key
from course_compiler.tracks import CANONICAL_TRACK_IDS
from course_compiler.verify import open_instructor_pack, verify_learner_pack

ROOT = Path(__file__).resolve().parents[2]
KEYS = ROOT / "contracts" / "fixtures" / "keys"
VK = KEYS / "TEST_ONLY_ed25519_public.key"
AES = KEYS / "TEST_ONLY_instructor_aes256.key"

# Representative subset + thin apprenticeship + DC regression
SECURITY_TRACKS = (
    "DIGITAL_CONFIDENCE",
    "IT_SUPPORT_HARDWARE",
    "SOFTWARE_BUILDER",
    "NETWORKING_INFRA",
    "CYBER_SOC",
    "SEVEN_GC_APPRENTICESHIP",
)


@pytest.mark.parametrize("track_id", SECURITY_TRACKS)
def test_signature_verify(tmp_path, track_id):
    out = tmp_path / track_id
    compile_module(track_id, out_dir=out)
    decision = verify_learner_pack(out, VK)
    assert decision.ok, decision.to_dict()
    # Tamper: flip one byte of a learner file hash entry by rewriting file
    learner_root = out / "learner"
    # Find a real content file (not manifests) if present
    candidates = [
        p
        for p in learner_root.rglob("*")
        if p.is_file() and p.name not in {"course_module.json", "canonical_track_reference.json", "compatibility.json"}
    ]
    if candidates:
        target = candidates[0]
        original = target.read_bytes()
        target.write_bytes(original + b"\x00")
        bad = verify_learner_pack(out, VK)
        assert not bad.ok
        target.write_bytes(original)


@pytest.mark.parametrize("track_id", SECURITY_TRACKS)
def test_aes_decrypt_instructor(tmp_path, track_id):
    out = tmp_path / track_id
    compile_module(track_id, out_dir=out)
    dec = open_instructor_pack(out, AES)
    assert dec.ok, dec.to_dict()
    # Direct decrypt path
    man = json.loads((out / "instructor_pack_manifest.json").read_text(encoding="utf-8"))
    enc_meta = man["encryption"]
    blob = (out / f"{track_id}.instructor.aes256gcm").read_bytes()
    plain = decrypt_aes_gcm(load_aes_key(AES), b64d(enc_meta["nonce_b64"]), blob)
    assert isinstance(plain, (bytes, bytearray))
    assert len(plain) > 0
    with zipfile.ZipFile(__import__("io").BytesIO(plain)) as zf:
        names = zf.namelist()
    # All archived paths must be relative (no absolute / escape)
    for name in names:
        assert not name.startswith("/"), name
        assert ".." not in Path(name).parts, name


@pytest.mark.parametrize("track_id", SECURITY_TRACKS)
def test_path_containment_learner_zip(tmp_path, track_id):
    out = tmp_path / track_id
    compile_module(track_id, out_dir=out)
    zpath = out / f"{track_id}.learner.zip"
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            name = info.filename
            assert not name.startswith("/"), name
            assert ".." not in Path(name).parts, name
            # No instructor tree in learner zip
            low = name.lower()
            assert "/instructor/" not in low
            assert "answer_keys.json" not in low


def test_all_canonical_ids_have_import_specs():
    imports = ROOT / "curriculum" / "imports"
    for tid in CANONICAL_TRACK_IDS:
        assert (imports / f"{tid}.import.json").is_file(), tid
