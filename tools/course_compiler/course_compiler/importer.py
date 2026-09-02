"""Import real WAIKE module sources using pinned globs — no invented curriculum."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .compat import RejectionReason
from .registry import RegistryError


INSTRUCTOR_NAME_HINTS = (
    "teaching_notes.md",
    "demo_plan.md",
    "answer_key",
    "solution_guide",
    "instructor_packet",
)


@dataclass
class ImportPlan:
    module_id: str
    source_commit: str
    learner_files: list[Path] = field(default_factory=list)
    instructor_files: list[Path] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)
    lessons: list[dict[str, Any]] = field(default_factory=list)


def load_import_spec(module_id: str, repo_root: Path) -> dict[str, Any]:
    path = repo_root / "curriculum" / "imports" / f"{module_id}.import.json"
    if not path.is_file():
        raise RegistryError(RejectionReason.UNKNOWN_MODULE, f"missing import spec {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _match_any(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def _is_instructor_path(rel: str, instructor_globs: list[str]) -> bool:
    if _match_any(rel, instructor_globs):
        return True
    name = Path(rel).name.lower()
    return any(h in name or name == h for h in INSTRUCTOR_NAME_HINTS)


def discover_files(waike_root: Path, spec: dict[str, Any]) -> ImportPlan:
    module_id = spec["module_id"]
    source_commit = spec["source_commit"]
    learner_globs = spec.get("learner_globs") or []
    instructor_globs = spec.get("instructor_only_globs") or []

    # Prefer explicit lesson tree existence
    lesson_root = waike_root / "lessons" / "by_course" / "digital_confidence"
    if module_id == "DIGITAL_CONFIDENCE" and not lesson_root.is_dir():
        raise RegistryError(
            RejectionReason.UNKNOWN_MODULE,
            f"DIGITAL_CONFIDENCE lessons missing at {lesson_root}",
        )

    candidates: set[Path] = set()
    for pat in learner_globs + instructor_globs:
        # Walk from waike root with limited depth via rglob on pattern prefix
        if "**" in pat:
            prefix = pat.split("**", 1)[0].rstrip("/")
            base = waike_root / prefix if prefix else waike_root
            if base.is_dir():
                for p in base.rglob("*"):
                    if p.is_file():
                        candidates.add(p)
            elif (waike_root / prefix).is_file():
                candidates.add(waike_root / prefix)
        else:
            # single path or simple glob
            matches = list(waike_root.glob(pat))
            for m in matches:
                if m.is_file():
                    candidates.add(m)
                elif m.is_dir():
                    candidates.update(p for p in m.rglob("*") if p.is_file())

    plan = ImportPlan(module_id=module_id, source_commit=source_commit)
    for path in sorted(candidates, key=lambda p: str(p).replace("\\", "/")):
        rel = path.relative_to(waike_root).as_posix()
        if path.name.startswith("."):
            continue
        instructor = _is_instructor_path(rel, instructor_globs)
        learner_match = _match_any(rel, learner_globs)
        if instructor:
            plan.instructor_files.append(path)
            if learner_match and any(h in Path(rel).name.lower() for h in ("teaching_notes", "demo_plan")):
                plan.excluded.append({"path": rel, "reason": "instructor_filename_override"})
            continue
        if learner_match:
            plan.learner_files.append(path)
        else:
            plan.excluded.append({"path": rel, "reason": "unmatched"})

    # Deduplicate while preserving order
    plan.learner_files = list(dict.fromkeys(plan.learner_files))
    plan.instructor_files = list(dict.fromkeys(plan.instructor_files))

    # Build lesson index from week folders
    weeks = sorted(lesson_root.glob("week_*")) if lesson_root.is_dir() else []
    for week_dir in weeks:
        m = re.match(r"week_(\d+)$", week_dir.name)
        if not m:
            continue
        week_num = int(m.group(1))
        lesson_plan = week_dir / "lesson_plan.md"
        if not lesson_plan.is_file():
            continue
        rel = lesson_plan.relative_to(waike_root).as_posix()
        plan.lessons.append(
            {
                "lesson_id": f"{module_id}_W{week_num:02d}",
                "title": f"Week {week_num}",
                "week": week_num,
                "order": week_num,
                "path": rel,
            }
        )
    if module_id == "DIGITAL_CONFIDENCE" and len(plan.lessons) < 8:
        raise RegistryError(
            RejectionReason.UNKNOWN_MODULE,
            f"expected 8 DIGITAL_CONFIDENCE weeks with lesson_plan.md, found {len(plan.lessons)}",
        )
    return plan
