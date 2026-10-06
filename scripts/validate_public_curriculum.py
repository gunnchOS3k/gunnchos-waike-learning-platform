#!/usr/bin/env python3
"""Fail closed if the browser catalog drifts from canonical registry/package evidence."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "apps/client/src/lib/product/publicCurriculum.ts"
REGISTRY = ROOT / "curriculum/registry/eighteen_tracks.json"
MATRIX = ROOT / "reports/WAIKE_18_TRACK_PACKAGE_MATRIX.json"
CONTENT = ROOT / "apps" / "client" / "src" / "generated" / "publicCurriculumContent.json"


def load_catalog_rows() -> list[list[object]]:
    rows: list[list[object]] = []
    in_rows = False
    for raw in CATALOG.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "export const PUBLIC_TRACKS: PublicTrack[] = [":
            in_rows = True
            continue
        if in_rows and line.startswith("].map("):
            break
        if in_rows and line.startswith("[") and line.endswith("],"):
            python_literal = line[:-1].replace("true", "True").replace("false", "False")
            rows.append(ast.literal_eval(python_literal))
    return rows


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    catalog = load_catalog_rows()
    canonical = registry.get("tracks") or []
    package_rows = {row["track"]: row for row in (matrix.get("rows") or [])}
    content_rows = {row["trackId"]: row for row in (content.get("tracks") or [])}

    errors: list[str] = []
    if len(catalog) != 18:
        errors.append(f"catalog_count={len(catalog)} expected=18")
    if len(canonical) != 18:
        errors.append(f"registry_count={len(canonical)} expected=18")

    catalog_ids = [str(row[0]) for row in catalog]
    canonical_ids = [str(row["track_id"]) for row in canonical]
    if catalog_ids != canonical_ids:
        errors.append("catalog order/IDs drift from canonical registry")

    for row, source in zip(catalog, canonical, strict=False):
        track_id, title = str(row[0]), str(row[1])
        if title != source.get("title"):
            errors.append(f"{track_id}: title drift")
        package = package_rows.get(track_id)
        if not package:
            errors.append(f"{track_id}: missing package matrix row")
            continue
        packaged_content = content_rows.get(track_id)
        if not packaged_content:
            errors.append(f"{track_id}: missing public authored-content row")
            continue
        expected_counts = [
            package.get("lessons"),
            package.get("assignments"),
            package.get("quizzes"),
            package.get("labs"),
            package.get("groups"),
            package.get("portfolio"),
        ]
        if row[4:10] != expected_counts:
            errors.append(f"{track_id}: activity counts drift")
        if bool(row[10]) != (package.get("offline") == "YES"):
            errors.append(f"{track_id}: offline declaration drift")
        if bool(row[11]) != (package.get("ai_policy") == "PRESENT"):
            errors.append(f"{track_id}: AI declaration drift")
        if package.get("verification") != "PASS" or package.get("learner_visible") != "PASS":
            errors.append(f"{track_id}: package is not verified learner-visible PASS")
        if packaged_content.get("contentRootSha256") != package.get("learner_hash"):
            errors.append(f"{track_id}: public content package hash drift")
        if packaged_content.get("sourceCommit") != package.get("source_sha"):
            errors.append(f"{track_id}: public content source commit drift")
        for kind, expected in zip(("lessons", "assignments", "quizzes", "labs"), expected_counts[:4], strict=True):
            items = packaged_content.get(kind) or []
            if len(items) != expected:
                errors.append(f"{track_id}: public {kind} count={len(items)} expected={expected}")
            if any(not str(item.get("markdown") or "").strip() for item in items):
                errors.append(f"{track_id}: empty public {kind} content")
        if not (packaged_content.get("portfolio") or []):
            errors.append(f"{track_id}: missing public portfolio content")

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "tracks": len(catalog),
                "registry_schema": registry.get("schema"),
                "package_version": matrix.get("package_version_default"),
                "real_content_bundle": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
