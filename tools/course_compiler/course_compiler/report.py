"""Import and verification report writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .jsonutil import dump_canonical
from .registry import repo_root


def write_import_report(
    plan_summary: dict[str, Any],
    pack_summary: dict[str, Any],
    *,
    reports_dir: Path | None = None,
) -> tuple[Path, Path]:
    reports = reports_dir or (repo_root() / "reports")
    reports.mkdir(parents=True, exist_ok=True)
    data = {
        "module_id": plan_summary["module_id"],
        "source_commit": plan_summary["source_commit"],
        "learner_file_count": plan_summary["learner_file_count"],
        "instructor_file_count": plan_summary["instructor_file_count"],
        "lessons": plan_summary["lessons"],
        "learner_files": plan_summary["learner_files"],
        "instructor_files": plan_summary["instructor_files"],
        "excluded": plan_summary.get("excluded") or [],
        "validation": "ok",
        "learner_content_root_sha256": pack_summary.get("learner_content_root_sha256"),
        "learner_pack_sha256": pack_summary.get("learner_pack_sha256"),
        "unsupported_facets": [],
    }
    json_path = reports / "digital_confidence_import_report.json"
    md_path = reports / "DIGITAL_CONFIDENCE_IMPORT_REPORT.md"
    dump_canonical(json_path, data)
    lines = [
        "# DIGITAL_CONFIDENCE import report",
        "",
        f"- Source commit: `{data['source_commit']}`",
        f"- Learner files: {data['learner_file_count']}",
        f"- Instructor files: {data['instructor_file_count']}",
        f"- Lessons: {len(data['lessons'])}",
        f"- Learner content root SHA-256: `{data['learner_content_root_sha256']}`",
        f"- Signed payload SHA-256: `{data['learner_pack_sha256']}`",
        "",
        "## Lessons",
        "",
    ]
    for lesson in data["lessons"]:
        lines.append(f"- {lesson['lesson_id']}: `{lesson['path']}`")
    lines.extend(["", "## Excluded / protected overrides", ""])
    for ex in data["excluded"][:50]:
        lines.append(f"- `{ex.get('path')}` — {ex.get('reason')}")
    if not data["excluded"]:
        lines.append("- (none recorded)")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
