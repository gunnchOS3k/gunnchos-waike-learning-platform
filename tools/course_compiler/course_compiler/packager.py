"""Build signed learner packs and encrypted instructor packs deterministically."""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import uuid
from pathlib import Path
from typing import Any

from . import __version__ as COMPILER_VERSION
from .compat import DEFAULT_COMPAT, PLATFORM_VERSION
from .crypto import b64, encrypt_aes_gcm, load_aes_key, load_signing_key, sign_bytes
from .hashutil import sha256_bytes, sha256_file, sha256_path_tree
from .importer import ImportPlan
from .jsonutil import dump_canonical, dumps_canonical, source_date_epoch_utc
from .registry import get_track, load_pin, load_taxonomy, repo_root, resolve_waike_root
from .schema_validate import validate_document


def _stable_course_uuid(module_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://waike.learning/course/{module_id}"))


def _copy_files(files: list[Path], waike_root: Path, dest_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for src in sorted(files, key=lambda p: p.relative_to(waike_root).as_posix()):
        rel = src.relative_to(waike_root).as_posix()
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        # normalize mtime for determinism when SOURCE_DATE_EPOCH set
        import os

        if os.environ.get("SOURCE_DATE_EPOCH"):
            ts = int(os.environ["SOURCE_DATE_EPOCH"])
            os.utime(dest, (ts, ts))
        entries.append({"path": rel, "sha256": sha256_file(dest), "size": dest.stat().st_size})
    return sorted(entries, key=lambda e: e["path"])


def _compat_for(role: str, source_commit: str, content_version: str, registry_hash: str) -> dict[str, Any]:
    compat = json.loads(json.dumps(DEFAULT_COMPAT))
    compat.update(
        {
            "registry_compat_version": "1.0.0",
            "registry_hash": registry_hash,
            "compiler_version": COMPILER_VERSION,
            "source_commit": source_commit,
            "package_role": role,
            "content_version": content_version,
            "client_min": PLATFORM_VERSION,
            "hub_min": PLATFORM_VERSION,
            "downgrade_policy": "reject",
        }
    )
    return compat


def build_packs(
    plan: ImportPlan,
    out_dir: Path,
    *,
    signing_key_path: Path,
    instructor_key_path: Path,
    public_key_id: str = "TEST_ONLY_ed25519",
    content_version: str = "1.0.0",
) -> dict[str, Any]:
    root = repo_root()
    pin = load_pin()
    waike_root = resolve_waike_root(pin)
    taxonomy = load_taxonomy(waike_root, pin)
    track = get_track(plan.module_id, taxonomy)
    registry_export = root / "curriculum" / "registry" / "CANONICAL_TRACK_REGISTRY.export.json"
    registry_hash = sha256_file(registry_export)

    out_dir.mkdir(parents=True, exist_ok=True)
    learner_dir = out_dir / "learner"
    instructor_dir = out_dir / "instructor"
    if learner_dir.exists():
        shutil.rmtree(learner_dir)
    if instructor_dir.exists():
        shutil.rmtree(instructor_dir)
    learner_content = learner_dir / "content"
    instructor_content = instructor_dir / "content"

    learner_files = _copy_files(plan.learner_files, waike_root, learner_content)
    instructor_files = _copy_files(plan.instructor_files, waike_root, instructor_content)

    course_uuid = _stable_course_uuid(plan.module_id)
    created = source_date_epoch_utc()
    pack_id_learner = f"{plan.module_id}.learner.{content_version}"
    pack_id_instructor = f"{plan.module_id}.instructor.{content_version}"

    module_doc = {
        "schema_version": "1.0.0",
        "module_id": plan.module_id,
        "track_id": plan.module_id,
        "title": track.get("title") or plan.module_id,
        "description": "Imported from pinned WAIKE checkout",
        "lessons": plan.lessons,
        "materials": [
            {"path": e["path"], "sha256": e["sha256"], "role": "learner"} for e in learner_files
        ],
    }
    decision = validate_document("course_module", module_doc)
    if not decision.ok:
        raise RuntimeError(f"course_module invalid: {decision.detail}")
    dump_canonical(learner_dir / "course_module.json", module_doc)

    # include module manifest in file list
    module_rel = "course_module.json"
    module_path = learner_dir / module_rel
    learner_files_with_module = learner_files + [
        {"path": module_rel, "sha256": sha256_file(module_path), "size": module_path.stat().st_size}
    ]
    learner_files_with_module = sorted(learner_files_with_module, key=lambda e: e["path"])

    content_paths = [e["path"] for e in learner_files]
    content_root_sha = sha256_path_tree(learner_content, content_paths)

    compat = _compat_for("learner", plan.source_commit, content_version, registry_hash)
    learner_manifest = {
        "schema_version": "1.0.0",
        "pack_id": pack_id_learner,
        "module_id": plan.module_id,
        "track_id": plan.module_id,
        "course_uuid": course_uuid,
        "role": "learner",
        "title": track.get("title") or plan.module_id,
        "content_version": content_version,
        "compiler_version": COMPILER_VERSION,
        "source_commit": plan.source_commit,
        "created_utc": created,
        "package_size_bytes": sum(e["size"] for e in learner_files_with_module),
        "client_min": PLATFORM_VERSION,
        "hub_min": PLATFORM_VERSION,
        "content_root_sha256": content_root_sha,
        "compatibility": compat,
        "files": learner_files_with_module,
        "license_refs": [],
        "provenance_refs": [f"waike-research-ops@{plan.source_commit}"],
    }
    d = validate_document("learner_pack_manifest", learner_manifest)
    if not d.ok:
        raise RuntimeError(f"learner manifest invalid: {d.detail}")
    dump_canonical(learner_dir / "manifest.json", learner_manifest)

    # Signed payload excludes volatile human notes; includes canonical manifest bytes
    signed_payload = dumps_canonical(learner_manifest).encode("utf-8")
    signing_key = load_signing_key(signing_key_path)
    signature = sign_bytes(signing_key, signed_payload)
    sig_meta = {
        "schema_version": "1.0.0",
        "alg": "Ed25519",
        "public_key_id": public_key_id,
        "role": "learner",
        "pack_id": pack_id_learner,
        "signature_b64": b64(signature),
        "signed_payload_sha256": sha256_bytes(signed_payload),
    }
    d = validate_document("package_signature_metadata", sig_meta)
    if not d.ok:
        raise RuntimeError(f"signature metadata invalid: {d.detail}")
    dump_canonical(learner_dir / "signature.json", sig_meta)

    # Instructor: tar content then encrypt
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
        for e in instructor_files:
            tar.add(instructor_content / e["path"], arcname=e["path"])
    plaintext = tar_buf.getvalue()
    aes_key = load_aes_key(instructor_key_path)
    # Fresh CSPRNG nonce every encryption; do not derive from SOURCE_DATE_EPOCH.
    nonce, ciphertext = encrypt_aes_gcm(aes_key, plaintext, pack_id_instructor.encode())

    (instructor_dir / "instructor_pack.bin").write_bytes(ciphertext)
    instructor_manifest = {
        "schema_version": "1.0.0",
        "pack_id": pack_id_instructor,
        "module_id": plan.module_id,
        "track_id": plan.module_id,
        "course_uuid": course_uuid,
        "role": "instructor",
        "title": track.get("title") or plan.module_id,
        "content_version": content_version,
        "compiler_version": COMPILER_VERSION,
        "source_commit": plan.source_commit,
        "created_utc": created,
        "package_size_bytes": len(ciphertext),
        "compatibility": _compat_for("instructor", plan.source_commit, content_version, registry_hash),
        "files": instructor_files,
        "encryption": {
            "alg": "AES-256-GCM",
            "nonce_b64": b64(nonce),
            "ciphertext_sha256": sha256_bytes(ciphertext),
            "plaintext_sha256": sha256_bytes(plaintext),
        },
    }
    d = validate_document("instructor_pack_manifest", instructor_manifest)
    if not d.ok:
        raise RuntimeError(f"instructor manifest invalid: {d.detail}")
    dump_canonical(instructor_dir / "manifest.json", instructor_manifest)

    return {
        "learner_dir": str(learner_dir),
        "instructor_dir": str(instructor_dir),
        "learner_manifest": learner_manifest,
        "instructor_manifest": instructor_manifest,
        "signature": sig_meta,
        "learner_content_root_sha256": content_root_sha,
        "learner_pack_sha256": sha256_bytes(signed_payload),
    }
