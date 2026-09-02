"""Verify learner packs before trust; open instructor packs with AES key."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from . import crypto
from .compat import CompatDecision, RejectionReason, check_compatibility_manifest
from .crypto import load_aes_key, load_verify_key
from .jsonutil import dumps_canonical


def _manifest_paths(pack_dir: Path) -> tuple[Path, Path]:
    # Compiler layout
    m1 = pack_dir / "learner_pack_manifest.json"
    s1 = pack_dir / "learner_pack.signature.json"
    if m1.is_file():
        return m1, s1
    # Alternate layout
    return pack_dir / "manifest.json", pack_dir / "signature.json"


def verify_learner_pack(pack_dir: Path, verify_key_path: Path) -> CompatDecision:
    manifest_path, sig_path = _manifest_paths(pack_dir)
    if not sig_path.is_file():
        return CompatDecision(False, RejectionReason.UNSIGNED_PACK, "signature missing")
    if not manifest_path.is_file():
        return CompatDecision(False, RejectionReason.MISSING_SIGNATURE, "manifest missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sig_meta = json.loads(sig_path.read_text(encoding="utf-8"))

    if manifest.get("role") != "learner":
        return CompatDecision(False, RejectionReason.WRONG_ROLE, f"role={manifest.get('role')}")

    sv = manifest.get("schema_version", "0.0.0")
    try:
        major = int(str(sv).split(".")[0])
    except ValueError:
        major = 0
    if major != 1:
        reason = RejectionReason.SCHEMA_DOWNGRADE if major < 1 else RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR
        return CompatDecision(False, reason, f"schema_version={sv}")

    d = check_compatibility_manifest(manifest.get("compatibility") or {})
    if not d.ok:
        return d

    payload = dumps_canonical(manifest).encode("utf-8")
    decision = crypto.verify_signature(load_verify_key(verify_key_path), payload, sig_meta)
    if not decision.ok:
        return decision

    learner_root = pack_dir / "learner"
    if not learner_root.is_dir():
        learner_root = pack_dir

    for entry in manifest.get("files") or []:
        rel = entry["path"]
        fpath = learner_root / rel
        if not fpath.is_file():
            fpath = pack_dir / rel
        if not fpath.is_file():
            return CompatDecision(False, RejectionReason.TAMPERED_CONTENT, f"missing file {rel}")
        digest = crypto.sha256_file(fpath)
        if digest != entry["sha256"]:
            return CompatDecision(False, RejectionReason.TAMPERED_CONTENT, f"hash mismatch {rel}")
        if fpath.stat().st_size != entry["size"]:
            return CompatDecision(False, RejectionReason.TAMPERED_CONTENT, f"size mismatch {rel}")
        low = rel.lower()
        if any(
            h in low
            for h in (
                "instructor_solution",
                "solution_guide",
                "solution_notes_for_instructors",
                "answer_key",
                "teaching_notes.md",
                "demo_plan.md",
                "test_only_ed25519_private",
            )
        ):
            return CompatDecision(
                False,
                RejectionReason.INSTRUCTOR_MATERIAL_IN_LEARNER,
                f"forbidden path in learner pack: {rel}",
            )

    return CompatDecision(True, detail="verified")


def open_instructor_pack(enc_or_dir, manifest_or_key=None, key_bytes: bytes | None = None) -> bytes | CompatDecision:
    """Open instructor pack.

    Supported call shapes:
    - open_instructor_pack(enc_path, manifest_path, key_bytes) -> plaintext bytes (raises ValueError)
    - open_instructor_pack(pack_dir, aes_key_path) -> CompatDecision
    """
    # Test API: (enc Path, man Path, key bytes)
    if key_bytes is not None:
        enc = Path(enc_or_dir)
        man = Path(manifest_or_key)
        manifest = json.loads(man.read_text(encoding="utf-8"))
        enc_meta = manifest.get("encryption") or {}
        try:
            nonce = crypto.b64d(enc_meta["nonce_b64"])
            return crypto.decrypt_aes_gcm(key_bytes, nonce, enc.read_bytes())
        except Exception as exc:
            raise ValueError("DECRYPT_FAILED") from exc

    pack_dir = Path(enc_or_dir)
    aes_key_path = Path(manifest_or_key)
    manifest_path = pack_dir / "instructor_pack_manifest.json"
    blob = pack_dir / "DIGITAL_CONFIDENCE.instructor.aes256gcm"
    if not blob.is_file():
        cands = list(pack_dir.glob("*.instructor.aes256gcm"))
        if not cands:
            return CompatDecision(False, RejectionReason.DECRYPT_FAILED, "instructor blob missing")
        blob = cands[0]
    if not manifest_path.is_file():
        return CompatDecision(False, RejectionReason.DECRYPT_FAILED, "instructor manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("role") != "instructor":
        return CompatDecision(False, RejectionReason.WRONG_ROLE, "not instructor pack")
    enc = manifest.get("encryption") or {}
    try:
        key = load_aes_key(aes_key_path)
        nonce = crypto.b64d(enc["nonce_b64"])
        plaintext = crypto.decrypt_aes_gcm(key, nonce, blob.read_bytes())
        with zipfile.ZipFile(io.BytesIO(plaintext)) as zf:
            _ = zf.namelist()
        return CompatDecision(True, detail=f"decrypted {len(plaintext)} bytes")
    except Exception as exc:
        return CompatDecision(False, RejectionReason.DECRYPT_FAILED, str(exc))


def reject_if_untrusted(decision: CompatDecision) -> None:
    if not decision.ok:
        raise PermissionError(decision.to_dict())
