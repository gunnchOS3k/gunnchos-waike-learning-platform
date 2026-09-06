"""Compile allow-listed WAIKE tracks into learner/instructor packs."""

from __future__ import annotations

import base64
import fnmatch
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable

from . import crypto
from .activity import inventory_from_paths, rubric_outcome_coverage
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
from .tracks import (
    CANONICAL_TRACK_IDS,
    DEFAULT_INSTRUCTOR_MARKERS,
    MIGRATION_METADATA,
    PACKAGE_VERSION,
)

INSTRUCTOR_NAME_HINTS = tuple(DEFAULT_INSTRUCTOR_MARKERS)

PRIVATE_KEY_HINTS = (".pem", ".key", "private_key", "PRIVATE", "TEST_ONLY_ed25519_private")

_WEEK_LEGACY_PLAN = re.compile(
    r"lessons/by_course/[^/]+/week_(\d+)/lesson_plan\.md$"
)
_WEEK_LEGACY_PRACTICE = re.compile(
    r"lessons/by_course/[^/]+/week_(\d+)/guided_practice\.md$"
)
_WEEK_RC_LESSON = re.compile(
    r"curriculum/digital_rc/[^/]+/weeks/w(\d+)/lesson\.md$"
)


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


def build_lessons(learner_rels: list[str], module_id: str = "DIGITAL_CONFIDENCE") -> list[dict[str, Any]]:
    """Index lessons from legacy digital_confidence week plans and digital_rc weeks/wNN."""
    lessons: list[dict[str, Any]] = []
    title_prefix = module_id.replace("_", " ").title()

    for rel in learner_rels:
        rel_n = rel.replace("\\", "/")
        m = _WEEK_LEGACY_PLAN.search(rel_n)
        if m:
            week_n = int(m.group(1))
            lessons.append(
                {
                    "lesson_id": f"{module_id}.W{week_n:02d}",
                    "title": f"{title_prefix} — Week {week_n}",
                    "path": rel_n,
                    "week": week_n,
                    "order": week_n,
                }
            )
            continue
        m = _WEEK_LEGACY_PRACTICE.search(rel_n)
        if m:
            week_n = int(m.group(1))
            lessons.append(
                {
                    "lesson_id": f"{module_id}.W{week_n:02d}.practice",
                    "title": f"Guided practice — Week {week_n}",
                    "path": rel_n,
                    "week": week_n,
                    "order": week_n * 10 + 1,
                }
            )
            continue
        m = _WEEK_RC_LESSON.search(rel_n)
        if m:
            week_n = int(m.group(1))
            lessons.append(
                {
                    "lesson_id": f"{module_id}.W{week_n:02d}",
                    "title": f"{title_prefix} — Week {week_n}",
                    "path": rel_n,
                    "week": week_n,
                    "order": week_n,
                }
            )

    lessons.sort(key=lambda x: (x.get("order", 0), x["lesson_id"]))
    # Prefer one primary lesson per week for UI navigation
    primary = [L for L in lessons if L["lesson_id"].count(".") == 1]
    return primary or lessons


def _write_import_report(root: Path, module_id: str, report: dict[str, Any], lessons: list[dict[str, Any]]) -> None:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    json_name = f"{module_id}_IMPORT_REPORT.json"
    md_name = f"{module_id}_IMPORT_REPORT.md"
    dump_canonical(reports / json_name, report)
    # Preserve legacy DIGITAL_CONFIDENCE report filenames used by Gate A verifiers
    if module_id == "DIGITAL_CONFIDENCE":
        dump_canonical(reports / "DIGITAL_CONFIDENCE_IMPORT_REPORT.json", report)
    md = [
        f"# {module_id} Import Report",
        "",
        f"- module_id: `{module_id}`",
        f"- declared_pinned_commit: `{report['declared_pinned_commit']}`",
        f"- observed_source_commit: `{report['observed_source_commit']}`",
        f"- provenance_match: `true`",
        f"- package_version: `{report.get('package_version')}`",
        f"- learner files: **{report['learner_file_count']}**",
        f"- instructor files: **{report['instructor_file_count']}**",
        f"- learner zip sha256: `{report['learner_zip_sha256']}`",
        f"- instructor plaintext sha256: `{report['instructor_plaintext_sha256']}`",
        f"- instructor ciphertext sha256 (non-reproducible): `{report['instructor_blob_sha256']}`",
        f"- lessons indexed: {len(lessons)}",
        f"- activity inventory: `{json.dumps(report.get('activity_inventory') or {}, sort_keys=True)}`",
        "",
        "## Lessons",
        "",
    ]
    for L in lessons:
        md.append(f"- `{L['lesson_id']}` — {L['title']} (`{L['path']}`)")
    md.append("")
    md.append("Keys used are TEST_ONLY fixtures. Not for production.")
    md.append("")
    (reports / md_name).write_text("\n".join(md), encoding="utf-8")
    if module_id == "DIGITAL_CONFIDENCE":
        (reports / "DIGITAL_CONFIDENCE_IMPORT_REPORT.md").write_text("\n".join(md), encoding="utf-8")


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
    pkg_version = str(import_spec.get("package_version") or PACKAGE_VERSION)
    migration = import_spec.get("migration") or dict(MIGRATION_METADATA)

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
    lessons = build_lessons(learner_rels, module_id=module_id)
    activity_inventory = inventory_from_paths(learner_rels + [e["path"] for e in instructor_entries])
    coverage = rubric_outcome_coverage(activity_inventory)

    module_doc = {
        "schema_version": "1.0.0",
        "module_id": module_id,
        "track_id": track.get("track_id", module_id),
        "title": track.get("title", module_id),
        "description": "Compiled from pinned WAIKE research-ops sources.",
        "package_version": pkg_version,
        "migration": migration,
        "lessons": lessons,
        "activity_inventory": activity_inventory,
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
        "package_version": pkg_version,
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
        "package_version": pkg_version,
        "migration": migration,
        "files": learner_entries,
        "compatibility": DEFAULT_COMPAT,
        "content_root_sha256": content_hash,
        "activity_inventory": activity_inventory,
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
        "package_version": pkg_version,
        "migration": migration,
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
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
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
        "package_version": pkg_version,
        "migration": migration,
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
        "activity_inventory": activity_inventory,
        "rubric_outcome_coverage": coverage,
        "verify_key_path": _rel(vk_path),
        "signing_key_warning": "TEST_ONLY",
    }
    _write_import_report(root, module_id, report, lessons)
    report["out_dir"] = str(out)
    return report


def compile_all(
    tracks: Iterable[str] | None = None,
    out_root: Path | None = None,
    signing_key_path: Path | None = None,
    instructor_key_path: Path | None = None,
) -> dict[str, Any]:
    """Compile each allow-listed track into out_root/<TRACK_ID>/."""
    root = repo_root()
    pin = load_pin()
    allowed = list(pin.get("module_ids_allowed") or list(CANONICAL_TRACK_IDS))
    selected = list(tracks) if tracks else allowed
    out_root = out_root or (root / "pack_out_18")
    results: dict[str, Any] = {"ok": True, "tracks": {}, "failures": []}
    for raw in selected:
        module_id = resolve_module_id(raw, pin)
        track_out = out_root / module_id
        try:
            report = compile_module(
                module_id,
                out_dir=track_out,
                signing_key_path=signing_key_path,
                instructor_key_path=instructor_key_path,
            )
            results["tracks"][module_id] = {"ok": True, "report": report}
        except Exception as exc:  # noqa: BLE001 — surface per-track status to CLI/matrix
            results["ok"] = False
            results["failures"].append({"track": module_id, "error": str(exc)})
            results["tracks"][module_id] = {"ok": False, "error": str(exc)}
    dump_canonical(
        root / "reports" / "COMPILE_ALL_18_REPORT.json",
        {
            "ok": results["ok"],
            "failures": results["failures"],
            "track_ids": list(results["tracks"].keys()),
            "statuses": {
                k: {"ok": v.get("ok"), "error": v.get("error")} for k, v in results["tracks"].items()
            },
        },
    )
    return results
