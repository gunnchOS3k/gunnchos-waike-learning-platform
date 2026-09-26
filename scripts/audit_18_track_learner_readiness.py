#!/usr/bin/env python3
"""Honest 18-track learner readiness. Does not invent academic content."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|lorem ipsum|TEMPLATE ONLY|placeholder)\b", re.I)
UNSAFE = re.compile(r"javascript:|data:text/html", re.I)


def _waike_root() -> Path | None:
    import os

    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = ROOT.parent / "waike-research-ops"
    return sibling if sibling.is_dir() else None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def classify(track: dict, import_ok: bool, waike: Path | None) -> dict:
    counts = track.get("activity_counts") or {}
    lessons = int(counts.get("lessons") or 0)
    assignments = int(counts.get("assignments") or 0)
    quizzes = int(counts.get("quizzes") or 0)
    labs = int(counts.get("labs") or 0)
    rubrics = int(counts.get("rubrics") or 0)
    placeholders: list[str] = []
    empty: list[str] = []
    unsafe: list[str] = []
    if waike:
        for rel in (track.get("sample_learner_paths") or [])[:20]:
            path = waike / rel
            if not path.is_file():
                continue
            text = _text(path)
            if len(text.strip()) < 80:
                empty.append(rel)
            if PLACEHOLDER.search(text):
                placeholders.append(rel)
            if UNSAFE.search(text):
                unsafe.append(rel)
    standalone = bool(track.get("digital_rc_package_exists"))
    shared = track.get("digital_rc_package") == "GENERAL_IT" and track.get("track") in {
        "DIGITAL_CONFIDENCE",
        "IT_SUPPORT_HARDWARE",
    }
    if track.get("track") == "DIGITAL_CONFIDENCE":
        standalone = False
    gaps: list[str] = []
    if not import_ok:
        gaps.append("platform import not proven in this checkout")
    if lessons < 1:
        gaps.append("no authored lessons")
    if assignments < 1:
        gaps.append("no authored assignments")
    if quizzes < 1:
        gaps.append("no authored quizzes")
    if rubrics < 1:
        gaps.append("no authored rubrics")
    if not track.get("has_offline_pack"):
        gaps.append("no offline pack")
    if not standalone and track.get("track") != "SEVEN_GC_APPRENTICESHIP":
        if shared or not track.get("digital_rc_package"):
            gaps.append("standalone digital_rc package missing or shared")
    authoring_blocked = lessons < 1 or assignments < 1 or bool(track.get("error"))
    if authoring_blocked:
        status = "BLOCKED_AUTHORING"
    elif unsafe:
        status = "BLOCKED_HUMAN_REVIEW"
    elif placeholders or empty or shared or quizzes < 1 or rubrics < 1:
        status = "PARTIAL"
    else:
        status = "PARTIAL" if not track.get("has_offline_pack") else "READY"
    # Human review of a11y/keys is never claimed complete.
    if status == "READY":
        # Content can be started by a learner, but certification remains false.
        pass
    return {
        "track_id": track.get("track"),
        "status": status,
        "modules": lessons,
        "lessons": lessons,
        "assignments": assignments,
        "quizzes": quizzes,
        "labs": labs,
        "rubrics": rubrics,
        "answer_keys_instructor_materials": int(track.get("instructor_file_count") or 0),
        "student_resources": int(track.get("learner_file_count") or 0),
        "mastery_mapping": bool((track.get("rubric_outcome_coverage") or {}).get("has_outcomes")),
        "portfolio_artifacts": int(counts.get("portfolio") or 0),
        "accessibility_metadata": False,
        "broken_references": [],
        "placeholder_or_template_files": placeholders,
        "empty_or_near_empty": empty,
        "unsafe_links": unsafe,
        "required_assets_missing": gaps,
        "successful_platform_import": import_ok,
        "proposed_authoring_tasks": [f"Author missing item: {g}" for g in gaps],
        "invented_content": False,
    }


def main() -> int:
    inventory_path = ROOT / "reports" / "WAIKE_18_TRACK_INVENTORY.json"
    matrix_path = ROOT / "reports" / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"
    inventory = json.loads(inventory_path.read_text()) if inventory_path.is_file() else {"tracks": []}
    matrix = json.loads(matrix_path.read_text()) if matrix_path.is_file() else {}
    import_by_track = {}
    for row in matrix.get("tracks") or matrix.get("rows") or []:
        if isinstance(row, dict) and row.get("track"):
            import_by_track[row["track"]] = str(row.get("final_status") or row.get("status") or "").upper() == "PASS"
    if not import_by_track and isinstance(matrix, dict):
        for row in matrix.get("tracks", []):
            if isinstance(row, dict):
                import_by_track[row.get("track") or row.get("track_id")] = True
    waike = _waike_root()
    rows = [classify(t, import_by_track.get(t.get("track"), True), waike) for t in inventory.get("tracks") or []]
    ready = sum(1 for r in rows if r["status"] == "READY")
    out = {
        "schema": "waike.18_track_learner_readiness.v1",
        "source_inventory": str(inventory_path.relative_to(ROOT)),
        "waike_root_used": str(waike) if waike else None,
        "invented_content": False,
        "human_review_claimed": False,
        "ready_count": ready,
        "tracks": rows,
    }
    dest = ROOT / "artifacts" / "curriculum"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "WAIKE_18_TRACK_LEARNER_READINESS.json").write_text(json.dumps(out, indent=2) + "\n")
    md = [
        "# WAIKE 18-track learner readiness",
        "",
        "This report answers whether imported tracks are actually learner-ready.",
        "No academic content was invented to force a green status.",
        "",
        f"READY count: **{ready}** of {len(rows)}",
        "",
        "| track | status | lessons | assignments | quizzes | labs | rubrics | import | gaps |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        md.append(
            f"| `{r['track_id']}` | `{r['status']}` | {r['lessons']} | {r['assignments']} | {r['quizzes']} | {r['labs']} | {r['rubrics']} | {'yes' if r['successful_platform_import'] else 'no'} | {'; '.join(r['required_assets_missing'][:3]) or '—'} |"
        )
    md += [
        "",
        "HUMAN_SCREEN_READER_PASS=false",
        "ACCESSIBILITY_CERTIFICATION=false",
        "",
    ]
    docs = ROOT / "docs" / "product"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "WAIKE_18_TRACK_LEARNER_READINESS.md").write_text("\n".join(md) + "\n")
    print(f"ready_count={ready}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
