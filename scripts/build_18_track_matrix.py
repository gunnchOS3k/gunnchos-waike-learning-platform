#!/usr/bin/env python3
"""Build the 18-track package matrix CSV/MD/JSON from compiled packs + inventory."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))
sys.path.insert(0, str(ROOT / "scripts"))

from course_compiler.activity import empty_counts  # noqa: E402
from course_compiler.compiler import compile_all  # noqa: E402
from course_compiler.crypto import sha256_file  # noqa: E402
from course_compiler.registry import load_pin, resolve_waike_root, verify_waike_provenance  # noqa: E402
from course_compiler.tracks import CANONICAL_TRACK_IDS, PACKAGE_VERSION  # noqa: E402
from course_compiler.verify import open_instructor_pack, verify_learner_pack  # noqa: E402
from inventory_18_tracks import inventory_track  # noqa: E402


MATRIX_COLUMNS = [
    "track",
    "source_sha",
    "package_version",
    "learner_hash",
    "instructor_hash",
    "verification",
    "decrypt",
    "lessons",
    "assignments",
    "quizzes",
    "labs",
    "discussions",
    "groups",
    "rubrics",
    "outcomes",
    "portfolio",
    "rubric_coverage",
    "outcome_coverage",
    "portfolio_mapping",
    "install",
    "learner_visible",
    "instructor_visible",
    "offline",
    "ai_policy",
    "final_status",
    "blocker",
]


def _keys() -> tuple[Path, Path]:
    keys = ROOT / "contracts" / "fixtures" / "keys"
    return keys / "TEST_ONLY_ed25519_public.key", keys / "TEST_ONLY_instructor_aes256.key"


def _row_for_track(
    track_id: str,
    *,
    source_sha: str,
    pack_dir: Path,
    compile_ok: bool,
    compile_error: str | None,
    inventory: dict | None,
) -> dict:
    vk, aes = _keys()
    counts = empty_counts()
    coverage = {"has_rubrics": False, "has_outcomes": False, "has_portfolio": False}
    has_ai = False
    has_offline = False
    if inventory:
        counts = dict(empty_counts())
        counts.update(inventory.get("activity_counts") or {})
        coverage = inventory.get("rubric_outcome_coverage") or coverage
        has_ai = bool(inventory.get("has_ai_policy"))
        has_offline = bool(inventory.get("has_offline_pack"))

    learner_hash = ""
    instructor_hash = ""
    verification = "FAIL"
    decrypt = "N/A"
    install = "FAIL"
    learner_visible = "FAIL"
    instructor_visible = "FAIL"
    blocker = compile_error or ""
    package_version = PACKAGE_VERSION

    if not compile_ok or not pack_dir.is_dir():
        return {
            "track": track_id,
            "source_sha": source_sha,
            "package_version": package_version,
            "learner_hash": learner_hash,
            "instructor_hash": instructor_hash,
            "verification": verification,
            "decrypt": decrypt,
            "lessons": counts["lessons"],
            "assignments": counts["assignments"],
            "quizzes": counts["quizzes"],
            "labs": counts["labs"],
            "discussions": counts["discussions"],
            "groups": counts["groups"],
            "rubrics": counts["rubrics"],
            "outcomes": counts["outcomes"],
            "portfolio": counts["portfolio"],
            "rubric_coverage": "YES" if coverage.get("has_rubrics") else "NO",
            "outcome_coverage": "YES" if coverage.get("has_outcomes") else "NO",
            "portfolio_mapping": "YES" if coverage.get("has_portfolio") else "THIN/NO",
            "install": install,
            "learner_visible": learner_visible,
            "instructor_visible": instructor_visible,
            "offline": "YES" if has_offline else "NO",
            "ai_policy": "PRESENT" if has_ai else "ABSENT",
            "final_status": "FAIL",
            "blocker": blocker or "compile_failed",
        }

    manifest_path = pack_dir / "learner_pack_manifest.json"
    if manifest_path.is_file():
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        package_version = str(man.get("package_version") or package_version)
        if man.get("activity_inventory"):
            counts.update(man["activity_inventory"])
        learner_hash = str(man.get("content_root_sha256") or "")
        learner_files = [e["path"] for e in (man.get("files") or [])]
        has_offline = has_offline or any("offline_pack" in p for p in learner_files)
        has_ai = has_ai or any("ai_use_policy" in p or "learner_ai_policy" in p for p in learner_files)

    zip_path = pack_dir / f"{track_id}.learner.zip"
    if zip_path.is_file() and not learner_hash:
        learner_hash = sha256_file(zip_path)

    decision = verify_learner_pack(pack_dir, vk)
    verification = "PASS" if decision.ok else f"FAIL:{decision.reason}"
    if decision.ok:
        install = "PASS"
        learner_visible = "PASS"

    enc = pack_dir / f"{track_id}.instructor.aes256gcm"
    im = pack_dir / "instructor_pack_manifest.json"
    if enc.is_file():
        instructor_hash = sha256_file(enc)
    if im.is_file():
        im_data = json.loads(im.read_text(encoding="utf-8"))
        instructor_hash = (im_data.get("encryption") or {}).get("ciphertext_sha256") or instructor_hash
        file_count = len(im_data.get("files") or [])
        dec = open_instructor_pack(pack_dir, aes)
        if getattr(dec, "ok", False):
            decrypt = "PASS"
            instructor_visible = "EMPTY" if file_count == 0 else "PASS"
        else:
            decrypt = f"FAIL:{getattr(dec, 'reason', 'DECRYPT')}"
            blocker = blocker or f"decrypt:{getattr(dec, 'detail', '')}"
    else:
        decrypt = "FAIL:missing_manifest"
        blocker = blocker or "missing instructor manifest"

    shell_only = (
        int(counts.get("lessons") or 0) == 0
        and int(counts.get("assignments") or 0) == 0
        and int(counts.get("quizzes") or 0) == 0
        and int(counts.get("labs") or 0) == 0
    )
    # SEVEN_GC shell-only (pre–PR #57) must stay BLOCKED. With COURSE_DIGITAL_RC
    # present on pinned WAIKE main, SEVEN_GC follows the normal digital PASS path.
    seven_gc_source_block = track_id == "SEVEN_GC_APPRENTICESHIP" and shell_only

    if decision.ok and decrypt.startswith("PASS"):
        if seven_gc_source_block:
            final = "BLOCKED"
            blocker = "SEVEN_GC_SOURCE_BLOCKS_18_OF_18"
        else:
            final = "PASS"
    else:
        final = "FAIL"

    if decision.ok and manifest_path.is_file():
        for e in json.loads(manifest_path.read_text(encoding="utf-8")).get("files") or []:
            low = e["path"].lower()
            if "/instructor/" in low or "answer_key" in low or low.endswith("teaching_notes.md"):
                final = "FAIL"
                blocker = f"instructor_leak:{e['path']}"
                learner_visible = "FAIL"
                break

    return {
        "track": track_id,
        "source_sha": source_sha,
        "package_version": package_version,
        "learner_hash": learner_hash,
        "instructor_hash": instructor_hash,
        "verification": verification,
        "decrypt": decrypt,
        "lessons": counts["lessons"],
        "assignments": counts["assignments"],
        "quizzes": counts["quizzes"],
        "labs": counts["labs"],
        "discussions": counts["discussions"],
        "groups": counts["groups"],
        "rubrics": counts["rubrics"],
        "outcomes": counts["outcomes"],
        "portfolio": counts["portfolio"],
        "rubric_coverage": "YES" if counts.get("rubrics", 0) > 0 else "NO",
        "outcome_coverage": "YES" if counts.get("outcomes", 0) > 0 else "NO",
        "portfolio_mapping": "YES" if counts.get("portfolio", 0) > 0 else "THIN/NO",
        "install": install,
        "learner_visible": learner_visible,
        "instructor_visible": instructor_visible,
        "offline": "YES" if has_offline else "NO",
        "ai_policy": "PRESENT" if has_ai else "ABSENT",
        "final_status": final,
        "blocker": blocker,
    }


def _write_md(rows: list[dict], path: Path, source_sha: str) -> None:
    lines = [
        "# WAIKE 18-Track Package Matrix",
        "",
        f"Source SHA (pinned/observed): `{source_sha}`",
        "",
        "| track | package | verify | decrypt | lessons | assigns | quizzes | labs | rubrics | portfolio | offline | AI | status | blocker |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {track} | {package_version} | {verification} | {decrypt} | {lessons} | {assignments} | "
            "{quizzes} | {labs} | {rubrics} | {portfolio} | {offline} | {ai_policy} | {final_status} | {blocker} |".format(
                **r
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    pin = load_pin()
    waike = resolve_waike_root(pin)
    provenance = verify_waike_provenance(pin, waike)
    source_sha = provenance["observed_source_commit"]

    imports_dir = ROOT / "curriculum" / "imports"
    inventory_by_track = {}
    for tid in CANONICAL_TRACK_IDS:
        spec = json.loads((imports_dir / f"{tid}.import.json").read_text(encoding="utf-8"))
        inventory_by_track[tid] = inventory_track(waike, tid, spec)

    inv_path = ROOT / "reports" / "WAIKE_18_TRACK_INVENTORY.json"
    inv_path.parent.mkdir(exist_ok=True)
    inv_path.write_text(
        json.dumps(
            {
                "pinned_commit": provenance["declared_pinned_commit"],
                "observed_source_commit": source_sha,
                "waike_root": str(waike),
                "tracks": [inventory_by_track[t] for t in CANONICAL_TRACK_IDS],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    out_root = ROOT / "pack_out_18"
    results = compile_all(tracks=list(CANONICAL_TRACK_IDS), out_root=out_root)

    rows = []
    for tid in CANONICAL_TRACK_IDS:
        payload = results["tracks"].get(tid) or {}
        rows.append(
            _row_for_track(
                tid,
                source_sha=source_sha,
                pack_dir=out_root / tid,
                compile_ok=bool(payload.get("ok")),
                compile_error=payload.get("error"),
                inventory=inventory_by_track.get(tid),
            )
        )

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    csv_path = reports / "WAIKE_18_TRACK_PACKAGE_MATRIX.csv"
    md_path = reports / "WAIKE_18_TRACK_PACKAGE_MATRIX.md"
    json_path = reports / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MATRIX_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in MATRIX_COLUMNS})

    _write_md(rows, md_path, source_sha)
    pass_n = sum(1 for r in rows if r["final_status"] == "PASS")
    blocked_n = sum(1 for r in rows if r["final_status"] == "BLOCKED")
    fail_n = sum(1 for r in rows if r["final_status"] not in {"PASS", "BLOCKED"})
    seven_gc_blocks = any(
        r["track"] == "SEVEN_GC_APPRENTICESHIP"
        and r["final_status"] == "BLOCKED"
        and "SEVEN_GC_SOURCE_BLOCKS_18_OF_18" in str(r.get("blocker") or "")
        for r in rows
    )
    all_18_pass = fail_n == 0 and blocked_n == 0 and pass_n == 18 and not seven_gc_blocks
    payload = {
        "source_sha": source_sha,
        "package_version_default": PACKAGE_VERSION,
        "columns": MATRIX_COLUMNS,
        "rows": rows,
        "summary": {
            "pass": pass_n,
            "blocked": blocked_n,
            "fail": fail_n,
            "tracks": len(rows),
            "full_18_course_digital_rc": all_18_pass,
            "SEVEN_GC_SOURCE_BLOCKS_18_OF_18": seven_gc_blocks,
            "ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE": all_18_pass,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Post–PR #57 honest matrix: all 18 digital PASS with SEVEN_GC COURSE_DIGITAL_RC.
    # Pre–PR #57 fallback: 17 PASS + SEVEN_GC BLOCKED remains acceptable if shell-only.
    honest_ok = (all_18_pass) or (fail_n == 0 and seven_gc_blocks and pass_n == 17)
    print(
        json.dumps(
            {
                "ok": honest_ok,
                "summary": payload["summary"],
                "csv": str(csv_path),
                "md": str(md_path),
                "json": str(json_path),
            },
            indent=2,
        )
    )
    return 0 if honest_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
