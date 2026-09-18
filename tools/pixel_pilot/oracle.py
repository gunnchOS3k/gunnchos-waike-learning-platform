#!/usr/bin/env python3
"""Self-diagnosing Pixel pilot oracle — classifies failures and writes DEFECT folders."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from tools.pixel_pilot import FAILURE_CLASSES

ROOT = Path(__file__).resolve().parents[2]
DEFECTS = ROOT / "artifacts" / "pixel6a_waike" / "defects"


def _ts() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def classify(message: str, *, default: str = "UNKNOWN_DEVIATION") -> str:
    m = (message or "").upper()
    rules = [
        ("MOCK_BACKEND", "MOCK_BACKEND_DETECTED"),
        ("MISSING_TRACK", "MISSING_TRACK"),
        ("MISSING_ROLE", "MISSING_ROLE"),
        ("LOGIN", "LOGIN_FAILURE"),
        ("AUTHZ", "AUTHZ_LEAK"),
        ("CROSS_SITE", "CROSS_SITE_LEAK"),
        ("WRONG_ROLE", "WRONG_ROLE_UI"),
        ("DEAD_CONTROL", "DEAD_CONTROL"),
        ("NO_STATE", "NO_STATE_MUTATION"),
        ("SUBMISSION", "SUBMISSION_FAILURE"),
        ("GRADEBOOK", "GRADEBOOK_FAILURE"),
        ("OFFLINE", "OFFLINE_FAILURE"),
        ("SYNC", "SYNC_FAILURE"),
        ("DUPLICATE", "DUPLICATE_SYNC"),
        ("PERSIST", "PERSISTENCE_FAILURE"),
        ("CRASH", "CRASH"),
        ("ANR", "ANR"),
        ("PERF", "PERFORMANCE_REGRESSION"),
        ("A11Y", "ACCESSIBILITY_MECHANIC_FAILURE"),
        ("LAYOUT", "VISUAL_LAYOUT_FAILURE"),
    ]
    for needle, klass in rules:
        if needle in m:
            return klass if klass in FAILURE_CLASSES else default
    return default if default in FAILURE_CLASSES else "UNKNOWN_DEVIATION"


def next_defect_id() -> str:
    DEFECTS.mkdir(parents=True, exist_ok=True)
    existing = sorted(DEFECTS.glob("DEFECT-*"))
    n = 1
    for p in existing:
        m = re.match(r"DEFECT-(\d+)", p.name)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f"DEFECT-{n:04d}"


def record_defect(
    *,
    expected: str,
    observed: str,
    failure_class: str | None = None,
    screenshot: Path | None = None,
    ui_hierarchy: str | None = None,
    console: str | None = None,
    hub_logs: str | None = None,
    db_probe: dict | None = None,
    reproduction: str = "",
    root_cause: str = "",
    fix_commit: str = "",
    retest: str = "pending",
) -> Path:
    klass = failure_class or classify(f"{expected} {observed}")
    if klass not in FAILURE_CLASSES:
        klass = "UNKNOWN_DEVIATION"
    did = next_defect_id()
    folder = DEFECTS / did
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "defect_id": did,
        "captured_at": _ts(),
        "failure_class": klass,
        "expected": expected,
        "observed": observed,
        "reproduction": reproduction,
        "root_cause": root_cause,
        "fix_commit": fix_commit,
        "retest": retest,
        "db_probe": db_probe or {},
    }
    (folder / "report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if ui_hierarchy:
        (folder / "ui_hierarchy.txt").write_text(ui_hierarchy, encoding="utf-8")
    if console:
        (folder / "browser_console.txt").write_text(console, encoding="utf-8")
    if hub_logs:
        (folder / "hub_logs.txt").write_text(hub_logs, encoding="utf-8")
    if screenshot and screenshot.is_file():
        dest = folder / screenshot.name
        dest.write_bytes(screenshot.read_bytes())
    return folder


if __name__ == "__main__":
    print(json.dumps({"failure_classes": list(FAILURE_CLASSES)}, indent=2))
