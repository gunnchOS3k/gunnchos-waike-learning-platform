#!/usr/bin/env python3
"""Inventory actual WAIKE content per canonical track (not directory existence alone)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))

from course_compiler.activity import inventory_from_paths, rubric_outcome_coverage  # noqa: E402
from course_compiler.compiler import collect_files, is_instructor_path  # noqa: E402
from course_compiler.registry import load_pin, resolve_waike_root, verify_waike_provenance  # noqa: E402
from course_compiler.tracks import CANONICAL_TRACK_IDS, digital_rc_folder  # noqa: E402


def inventory_track(waike: Path, track_id: str, import_spec: dict) -> dict:
    learner_globs = import_spec.get("learner_globs") or []
    instructor_globs = import_spec.get("instructor_only_globs") or []
    markers = import_spec.get("instructor_path_markers")
    learner_candidates = collect_files(waike, learner_globs)
    instructor_extra = collect_files(waike, instructor_globs)
    learner_rels: list[str] = []
    instructor_rels: list[str] = []
    for path in set(learner_candidates) | set(instructor_extra):
        rel = path.relative_to(waike).as_posix()
        if is_instructor_path(rel, instructor_globs, markers):
            instructor_rels.append(rel)
        else:
            learner_rels.append(rel)
    counts = inventory_from_paths(learner_rels + instructor_rels)
    coverage = rubric_outcome_coverage(counts)
    pkg = digital_rc_folder(track_id)
    pkg_exists = bool(pkg and (waike / "curriculum" / "digital_rc" / pkg).is_dir())
    return {
        "track": track_id,
        "source_kind": import_spec.get("source_kind"),
        "digital_rc_package": pkg,
        "digital_rc_package_exists": pkg_exists,
        "learner_file_count": len(learner_rels),
        "instructor_file_count": len(instructor_rels),
        "activity_counts": counts,
        "rubric_outcome_coverage": coverage,
        "has_ai_policy": any(
            rel.endswith("ai_use_policy.json") or "/guides/learner_ai_policy.md" in rel
            for rel in learner_rels
        ),
        "has_offline_pack": any("/offline_pack/" in rel or rel.endswith("offline_pack/pack.json") for rel in learner_rels),
        "sample_learner_paths": sorted(learner_rels)[:12],
        "sample_instructor_paths": sorted(instructor_rels)[:8],
    }


def main() -> int:
    pin = load_pin()
    waike = resolve_waike_root(pin)
    provenance = verify_waike_provenance(pin, waike)
    imports_dir = ROOT / "curriculum" / "imports"
    rows = []
    for track_id in CANONICAL_TRACK_IDS:
        spec_path = imports_dir / f"{track_id}.import.json"
        if not spec_path.is_file():
            rows.append(
                {
                    "track": track_id,
                    "error": f"missing import spec {spec_path.name}",
                    "activity_counts": {},
                }
            )
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        rows.append(inventory_track(waike, track_id, spec))

    out = {
        "pinned_commit": provenance["declared_pinned_commit"],
        "observed_source_commit": provenance["observed_source_commit"],
        "waike_root": str(waike),
        "tracks": rows,
    }
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / "WAIKE_18_TRACK_INVENTORY.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "tracks": len(rows), "report": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
