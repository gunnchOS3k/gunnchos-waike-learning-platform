"""Compile DIGITAL_CONFIDENCE (and allow-listed modules) into learner/instructor packs."""

from __future__ import annotations

import fnmatch
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable

from . import crypto
from .compat import DEFAULT_COMPAT
from .jsonutil import dump_canonical, dumps_canonical, source_date_epoch_utc, zip_write_file
from .registry import (
    assert_signing_key_allowed,
    get_track,
    load_pin,
    load_taxonomy,
    repo_root,
    resolve_module_id,
    resolve_waike_root,
    verify_waike_provenance,
)

INSTRUCTOR_NAME_HINTS = (
    "instructor_solution",
    "instructor_solution_guide",
    "instructor_solution_guides",
    "solution_guide",
    "solution_notes_for_instructors",
    "instructor_notes",
    "answer_key",
    "answer_keys",
    "/instructor/",
    "instructor_packet",
    "deep_instructor",
    "teaching_notes.md",
    "demo_plan.md",
)

PRIVATE_KEY_HINTS = (".pem", ".key", "private_key", "PRIVATE", "TEST_ONLY_ed25519_private")


def _match_any(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.rstrip("/") + "/**") for p in patterns)


def is_instructor_path(rel: str, instructor_globs: list[str], markers: list[str] | None = None) -> bool:
    if _match_any(rel, instructor_globs):
        return True
    low = rel.replace("\\", "/").lower()
    hints = markers or list(INSTRUCTOR_NAME_HINTS)
    return any(h.lower() in low for h in hints)


def collect_files(waike_root: Path, patterns: list[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        # Support directory prefixes ending with /
        if pattern.endswith("/"):
            base = waike_root / pattern
            if base.is_dir():
                for p in base.rglob("*"):
                    if p.is_file():
                        found.add(p)
            continue
        for p in waike_root.glob(pattern):
            if p.is_file():
                found.add(p)
            elif p.is_dir():
                for c in p.rglob("*"):
                    if c.is_file():
                        found.add(c)
    return sorted(found, key=lambda p: str(p.relative_to(waike_root)).replace("\\", "/"))


def build_lessons(learner_rels: list[str]) -> list[dict[str, Any]]:
    lessons = []
    for rel in learner_rels:
        if "/lessons/by_course/digital_confidence/week_" in rel and rel.endswith("lesson_plan.md"):
            week = rel.split("week_")[1].split("/")[0]
            try:
                week_n = int(week)
            except ValueError:
                week_n = 0
            lessons.append(
                {
                    "lesson_id": f"DIGITAL_CONFIDENCE.W{week_n:02d}",
                    "title": f"Digital Confidence — Week {week_n}",
                    "path": rel,
                    "week": week_n,
                    "order": week_n,
                }
            )
        elif rel.endswith("guided_practice.md") and "digital_confidence/week_" in rel:
            week = rel.split("week_")[1].split("/")[0]
            try:
                week_n = int(week)
            except ValueError:
                continue
            lessons.append(
                {
                    "lesson_id": f"DIGITAL_CONFIDENCE.W{week_n:02d}.practice",
                    "title": f"Guided practice — Week {week_n}",
                    "path": rel,
                    "week": week_n,
                    "order": week_n * 10 + 1,
                }
            )
    lessons.sort(key=lambda x: (x.get("order", 0), x["lesson_id"]))
    # Prefer one primary lesson_plan per week for UI navigation
    primary = [L for L in lessons if L["lesson_id"].count(".") == 1]
    return primary or lessons


def compile_module(
    module_raw: str,
    out_dir: Path | None = None,
    signing_key_path: Path | None = None,
    instructor_key_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root()
    pin = load_pin()
    module_id = resolve_module_id(module_raw, pin)
    waike = resolve_waike_root(pin)
    # Gate 2: never claim PIN provenance without verifying observed checkout HEAD.
    provenance = verify_waike_provenance(pin, waike)
    taxonomy = load_taxonomy(waike, pin)
    track = get_track(module_id, taxonomy)

    import_path = root / "curriculum" / "imports" / f"{module_id}.import.json"
    import_spec = json.loads(import_path.read_text(encoding="utf-8"))

    learner_globs = import_spec.get("learner_globs") or []
    instructor_globs = import_spec.get("instructor_only_globs") or []
    markers = import_spec.get("instructor_path_markers")
    # Collect learner candidates and instructor-only paths separately (fail closed / scoped).
    learner_candidates = collect_files(waike, learner_globs)
    instructor_extra = collect_files(waike, instructor_globs)
    all_files = sorted(set(learner_candidates) | set(instructor_extra), key=lambda p: p.as_posix())

    learner_files: list[Path] = []
    instructor_files: list[Path] = []
    for path in all_files:
        rel = path.relative_to(waike).as_posix()
        if is_instructor_path(rel, instructor_globs, markers):
            instructor_files.append(path)
        else:
            learner_files.append(path)

    out = out_dir or (root / "curriculum" / "imports" / module_id / "build")
    if out.exists():
        shutil.rmtree(out)
    learner_root = out / "learner"
    instructor_root = out / "instructor"
    learner_root.mkdir(parents=True)
    instructor_root.mkdir(parents=True)

    def copy_set(files: list[Path], dest_root: Path) -> list[dict[str, Any]]:
        entries = []
        for src in files:
            rel = src.relative_to(waike).as_posix()
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            digest = crypto.sha256_file(dest)
            entries.append({"path": rel, "sha256": digest, "size": dest.stat().st_size})
        entries.sort(key=lambda e: e["path"])
        return entries

    learner_entries = copy_set(learner_files, learner_root)
    instructor_entries = copy_set(instructor_files, instructor_root)

    # Safety scan: no private keys / instructor hints in learner
    for e in learner_entries:
        low = e["path"].lower()
        if any(h.lower() in low for h in PRIVATE_KEY_HINTS):
            raise RuntimeError(f"private key material leaked into learner pack: {e['path']}")
        if is_instructor_path(e["path"], instructor_globs, markers):
            raise RuntimeError(f"instructor path leaked into learner pack: {e['path']}")

    created = source_date_epoch_utc()
    learner_rels = [e["path"] for e in learner_entries]
    lessons = build_lessons(learner_rels)

    module_doc = {
        "schema_version": "1.0.0",
        "module_id": module_id,
        "track_id": track.get("track_id", module_id),
        "title": track.get("title", module_id),
        "description": "Compiled from pinned WAIKE research-ops sources.",
        "lessons": lessons,
        "materials": [
            {"path": e["path"], "sha256": e["sha256"], "role": "learner", "media_type": "text/markdown"}
            for e in learner_entries
        ],
    }
    dump_canonical(learner_root / "course_module.json", module_doc)

    track_ref = {
        "schema_version": "1.0.0",
        "track_id": track.get("track_id", module_id),
        "requirement_id": track.get("requirement_id"),
        "title": track.get("title"),
        "academy_id": track.get("academy_id", "ACADEMY_IT"),
        "extension_class": track.get("extension_class"),
        "owner_program_file": track.get("owner_program_file"),
        "aliases": [k for k, v in (pin.get("aliases") or {}).items() if v == module_id],
        "source_commit": pin.get("pinned_commit"),
    }
    dump_canonical(learner_root / "canonical_track_reference.json", track_ref)
    dump_canonical(learner_root / "compatibility.json", DEFAULT_COMPAT)

    # Re-hash after adding manifests
    for extra in ("course_module.json", "canonical_track_reference.json", "compatibility.json"):
        p = learner_root / extra
        learner_entries.append(
            {"path": extra, "sha256": crypto.sha256_file(p), "size": p.stat().st_size}
        )
    learner_entries.sort(key=lambda e: e["path"])

    content_hash = crypto.sha256_bytes(
        dumps_canonical({"files": learner_entries}).encode("utf-8")
    )

    learner_manifest = {
        "schema_version": "1.0.0",
        "pack_id": f"{module_id}.learner.v1",
        "module_id": module_id,
        "role": "learner",
        "title": track.get("title", module_id),
        "created_utc": created,
        "source_commit": pin.get("pinned_commit"),
        "files": learner_entries,
        "compatibility": DEFAULT_COMPAT,
        "content_root_sha256": content_hash,
    }
    dump_canonical(out / "learner_pack_manifest.json", learner_manifest)

    keys_dir = root / "contracts" / "fixtures" / "keys"
    sk_path = signing_key_path or (keys_dir / "TEST_ONLY_ed25519_private.key")
    vk_path = keys_dir / "TEST_ONLY_ed25519_public.key"
    aes_path = instructor_key_path or (keys_dir / "TEST_ONLY_instructor_aes256.key")
    assert_signing_key_allowed(sk_path, release_mode=False)
    signing_key = crypto.load_signing_key(sk_path)
    payload, sig_meta = crypto.sign_manifest_dict(signing_key, learner_manifest)
    dump_canonical(out / "learner_pack.signature.json", sig_meta)
    (out / "learner_pack.manifest.canonical.json").write_bytes(payload)

    # Zip learner pack (deterministic ZipInfo timestamps under SOURCE_DATE_EPOCH)
    zip_path = out / f"{module_id}.learner.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for e in sorted(learner_entries, key=lambda x: x["path"]):
            zip_write_file(zf, learner_root / e["path"], e["path"])
        zip_write_file(zf, out / "learner_pack_manifest.json", "learner_pack_manifest.json")
        zip_write_file(zf, out / "learner_pack.signature.json", "learner_pack.signature.json")

    # Instructor pack: encrypt tree as single blob
    instructor_manifest = {
        "schema_version": "1.0.0",
        "pack_id": f"{module_id}.instructor.v1",
        "module_id": module_id,
        "role": "instructor",
        "title": f"{track.get('title', module_id)} (instructor)",
        "created_utc": created,
        "source_commit": pin.get("pinned_commit"),
        "files": instructor_entries,
        "compatibility": DEFAULT_COMPAT,
    }
    # Build instructor zip bytes then encrypt
    instructor_zip = out / f"{module_id}.instructor.plain.zip"
    with zipfile.ZipFile(instructor_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for e in sorted(instructor_entries, key=lambda x: x["path"]):
            zip_write_file(zf, instructor_root / e["path"], e["path"])
        dump_canonical(out / "instructor_pack_manifest.inner.json", instructor_manifest)
        zip_write_file(zf, out / "instructor_pack_manifest.inner.json", "instructor_pack_manifest.json")

    plain = instructor_zip.read_bytes()
    instructor_plaintext_sha256 = crypto.sha256_bytes(plain)
    instructor_manifest_sha256 = crypto.sha256_bytes(
        dumps_canonical(instructor_manifest).encode("utf-8")
    )
    (out / "instructor_plaintext.sha256").write_text(instructor_plaintext_sha256 + "\n", encoding="utf-8")
    (out / "instructor_manifest.canonical.sha256").write_text(
        instructor_manifest_sha256 + "\n", encoding="utf-8"
    )
    # AES-GCM: fresh CSPRNG nonce every encryption; ciphertext is NOT reproducible.
    nonce, ciphertext = crypto.encrypt_aes_gcm(crypto.load_aes_key(aes_path), plain)
    enc_path = out / f"{module_id}.instructor.aes256gcm"
    enc_path.write_bytes(ciphertext)
    instructor_manifest["encryption"] = {
        "alg": "AES-256-GCM",
        "nonce_b64": __import__("base64").b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": crypto.sha256_bytes(ciphertext),
        "plaintext_sha256": instructor_plaintext_sha256,
        "manifest_sha256": instructor_manifest_sha256,
    }
    dump_canonical(out / "instructor_pack_manifest.json", instructor_manifest)
    instructor_zip.unlink(missing_ok=True)

    def _rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(root))
        except ValueError:
            return str(p.resolve())

    report = {
        "module_id": module_id,
        "declared_pinned_commit": provenance["declared_pinned_commit"],
        "observed_source_commit": provenance["observed_source_commit"],
        "source_commit": provenance["observed_source_commit"],
        "provenance_match": True,
        "waike_root": str(waike),
        "learner_file_count": len(learner_entries),
        "instructor_file_count": len(instructor_entries),
        "learner_zip": _rel(zip_path),
        "learner_zip_sha256": crypto.sha256_file(zip_path),
        "instructor_blob": _rel(enc_path),
        "instructor_blob_sha256": crypto.sha256_file(enc_path),
        "instructor_plaintext_sha256": instructor_plaintext_sha256,
        "instructor_manifest_sha256": instructor_manifest_sha256,
        "lessons": lessons,
        "verify_key_path": _rel(vk_path),
        "signing_key_warning": "TEST_ONLY",
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    dump_canonical(reports / "DIGITAL_CONFIDENCE_IMPORT_REPORT.json", report)
    md = [
        f"# DIGITAL_CONFIDENCE Import Report",
        "",
        f"- module_id: `{module_id}`",
        f"- declared_pinned_commit: `{provenance['declared_pinned_commit']}`",
        f"- observed_source_commit: `{provenance['observed_source_commit']}`",
        f"- provenance_match: `true`",
        f"- learner files: **{len(learner_entries)}**",
        f"- instructor files: **{len(instructor_entries)}**",
        f"- learner zip sha256: `{report['learner_zip_sha256']}`",
        f"- instructor plaintext sha256: `{instructor_plaintext_sha256}`",
        f"- instructor ciphertext sha256 (non-reproducible): `{report['instructor_blob_sha256']}`",
        f"- lessons indexed: {len(lessons)}",
        "",
        "## Lessons",
        "",
    ]
    for L in lessons:
        md.append(f"- `{L['lesson_id']}` — {L['title']} (`{L['path']}`)")
    md.append("")
    md.append("Keys used are TEST_ONLY fixtures. Not for production.")
    md.append("")
    (reports / "DIGITAL_CONFIDENCE_IMPORT_REPORT.md").write_text("\n".join(md), encoding="utf-8")
    report["out_dir"] = str(out)
    return report
