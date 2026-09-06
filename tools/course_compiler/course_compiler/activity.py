"""Activity inventory counting from compiled / source path lists."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

ACTIVITY_KEYS = (
    "lessons",
    "assignments",
    "quizzes",
    "labs",
    "discussions",
    "groups",
    "rubrics",
    "outcomes",
    "portfolio",
)

_WEEK_LEGACY = re.compile(r"(?:^|/)lessons/by_course/[^/]+/week_(\d+)/lesson_plan\.md$")
_WEEK_RC = re.compile(r"(?:^|/)curriculum/digital_rc/[^/]+/weeks/w(\d+)/lesson\.md$")
_ASSIGN_RC = re.compile(r"(?:^|/)curriculum/digital_rc/[^/]+/assignments/[^/]+\.(md|json)$", re.I)
_ASSIGN_LEGACY = re.compile(
    r"(?:^|/)(assignments|assignment_bodies)/by_course/[^/]+/.+\.(md|json|yaml|yml)$",
    re.I,
)
_QUIZ_RC = re.compile(r"(?:^|/)curriculum/digital_rc/[^/]+/quizzes/[^/]+\.(json|md)$", re.I)
_LAB_RC = re.compile(r"(?:^|/)curriculum/digital_rc/[^/]+/labs/(lab_[^/]+)/", re.I)
_LAB_LEGACY = re.compile(r"(?:^|/)labs/by_course/[^/]+/", re.I)
_RUBRIC = re.compile(r"(?:^|/)rubrics/[^/]+\.(md|json)$", re.I)
_PORTFOLIO = re.compile(r"(?:^|/)portfolio/", re.I)
_GROUP = re.compile(r"(group_project|group_projects|(?:^|/)projects/group)", re.I)
_DISCUSSION = re.compile(r"(?:^|/)discussions?/(?:|/)|/discussion_", re.I)
_OUTCOME = re.compile(
    r"(career_mapping|credential|outcomes|learning_outcomes|final_practical|final_knowledge|mid_course)",
    re.I,
)


def _norm(rel: str) -> str:
    return rel.replace("\\", "/")


def classify_path(rel: str) -> str | None:
    """Return primary activity type for a relative path, or None."""
    p = _norm(rel)
    low = p.lower()
    name = Path(p).name.lower()

    if _WEEK_LEGACY.search(p) or (_WEEK_RC.search(p)):
        return "lessons"
    if name == "lesson_plan.md" and "/week_" in p:
        return "lessons"
    if name == "lesson.md" and "/weeks/w" in p:
        return "lessons"
    if _ASSIGN_RC.search(p) or _ASSIGN_LEGACY.search(p):
        return "assignments"
    if _QUIZ_RC.search(p):
        return "quizzes"
    if "/quizzes/" in low and name.endswith((".json", ".md")) and "instructor" not in low:
        return "quizzes"
    if _LAB_RC.search(p):
        if name.endswith((".md", ".json", ".py", ".sh")) or name == "readme.md":
            return "labs"
    if _LAB_LEGACY.search(p) and name.endswith(".md"):
        return "labs"
    if _DISCUSSION.search(p):
        return "discussions"
    if _GROUP.search(p):
        return "groups"
    if _RUBRIC.search(p) and name != "rubrics.json":
        return "rubrics"
    if ("portfolio" in low) and name.endswith((".md", ".json")) and "instructor" not in low:
        # digital_rc/.../portfolio/PORTFOLIO.md or portfolio/by_track/...
        if "/portfolio/" in low or low.startswith("portfolio/"):
            return "portfolio"
    if _OUTCOME.search(p) and name.endswith((".md", ".json")):
        return "outcomes"
    return None


def inventory_from_paths(rels: Iterable[str]) -> dict[str, int]:
    """Count activity units from relative paths (deduped by activity identity)."""
    seen: dict[str, set[str]] = {k: set() for k in ACTIVITY_KEYS}
    for rel in rels:
        p = _norm(rel)
        kind = classify_path(p)
        if kind is None:
            continue
        if kind == "labs":
            m = _LAB_RC.search(p)
            if m:
                key = m.group(1)
            else:
                # legacy labs/by_course/<course>/<lab_or_week>/...
                parts = p.split("/")
                if "labs" in parts and "by_course" in parts:
                    try:
                        i = parts.index("by_course")
                        key = "/".join(parts[i : i + 3])  # by_course/<course>/<unit>
                    except (ValueError, IndexError):
                        key = p
                else:
                    key = p
            seen["labs"].add(key.lower())
        elif kind == "lessons":
            m = _WEEK_LEGACY.search(p) or _WEEK_RC.search(p)
            if m:
                seen["lessons"].add(f"w{int(m.group(1)):02d}")
            else:
                m2 = re.search(r"/weeks/w(\d+)/", p) or re.search(r"/week_(\d+)/", p)
                if m2:
                    seen["lessons"].add(f"w{int(m2.group(1)):02d}")
                else:
                    seen["lessons"].add(p.lower())
        else:
            seen[kind].add(Path(p).name.lower() if kind != "portfolio" else p.lower())
    return {k: len(seen[k]) for k in ACTIVITY_KEYS}


def rubric_outcome_coverage(counts: dict[str, int]) -> dict[str, bool]:
    return {
        "has_rubrics": counts.get("rubrics", 0) > 0,
        "has_outcomes": counts.get("outcomes", 0) > 0,
        "has_portfolio": counts.get("portfolio", 0) > 0,
    }


def empty_counts() -> dict[str, int]:
    return {k: 0 for k in ACTIVITY_KEYS}
