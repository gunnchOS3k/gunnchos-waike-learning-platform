#!/usr/bin/env python3
"""Build the no-Hub browser reader from verified learner-pack payloads."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "pack_out_18"
REGISTRY = ROOT / "curriculum" / "registry" / "eighteen_tracks.json"
MATRIX = ROOT / "reports" / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"
OUTPUT = ROOT / "apps" / "client" / "src" / "generated" / "publicCurriculumContent.json"


def heading(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return fallback


def json_as_markdown(raw: str, fallback: str) -> tuple[str, str]:
    data = json.loads(raw)
    week = data.get("week")
    title = f"Quiz {week}" if week is not None else fallback
    lines = [f"# {title}", ""]
    for number, item in enumerate(data.get("items") or [], 1):
        lines.extend([f"## {number}. {item.get('stem', 'Question')}", ""])
        for choice in item.get("choices") or []:
            lines.append(f"- {choice}")
        lines.append("")
    return title, "\n".join(lines).rstrip() + "\n"


def content_item(pack_dir: Path, path: str, kind: str, number: int) -> dict[str, Any]:
    source = pack_dir / "learner" / path
    raw = source.read_text(encoding="utf-8")
    fallback = f"{kind.title()} {number}"
    if source.suffix == ".json":
        title, markdown = json_as_markdown(raw, fallback)
    else:
        title, markdown = heading(raw, fallback), raw
    return {
        "id": f"{kind}-{number}",
        "title": title,
        "path": path,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "markdown": markdown,
    }


def select(paths: list[str], predicate: Callable[[str], bool]) -> list[str]:
    return sorted(path for path in paths if predicate(path))


def build_track(track: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    track_id = track["track_id"]
    pack_dir = PACKS / track_id
    manifest = json.loads((pack_dir / "learner_pack_manifest.json").read_text(encoding="utf-8"))
    paths = [entry["path"] for entry in manifest.get("files") or []]
    digital_confidence = track_id == "DIGITAL_CONFIDENCE"

    if digital_confidence:
        lesson_paths = select(paths, lambda p: "/GENERAL_IT/weeks/" in p and p.endswith("/lesson.md"))
        assignment_paths = select(paths, lambda p: "/GENERAL_IT/assignments/" in p and p.endswith(".md"))
        lab_paths = select(paths, lambda p: "/GENERAL_IT/labs/" in p and p.endswith("/README.md"))
        portfolio_paths = select(
            paths,
            lambda p: (
                p.startswith("portfolio/by_track/")
                or "/DIGITAL_CONFIDENCE/portfolio/" in p
            ) and p.endswith(".md"),
        )
    else:
        lesson_paths = select(paths, lambda p: "/presentation/week_" in p and p.endswith(".md"))
        assignment_paths = select(paths, lambda p: "/assignments/" in p and p.endswith(".md"))
        lab_paths = select(paths, lambda p: "/labs/" in p and p.endswith("/README.md"))
        portfolio_paths = select(paths, lambda p: "/portfolio/" in p and p.endswith(".md"))
    quiz_paths = select(paths, lambda p: "/quizzes/" in p and p.endswith(".json"))

    selected = {
        "lessons": lesson_paths,
        "assignments": assignment_paths,
        "quizzes": quiz_paths,
        "labs": lab_paths,
        "portfolio": portfolio_paths,
    }
    for kind in ("lessons", "assignments", "quizzes", "labs"):
        expected = int(matrix[kind])
        actual = len(selected[kind])
        if actual != expected:
            raise RuntimeError(f"{track_id}:{kind} selected={actual} expected={expected}")
    if not portfolio_paths:
        raise RuntimeError(f"{track_id}: no learner portfolio content selected")

    return {
        "trackId": track_id,
        "title": track["title"],
        "packId": manifest["pack_id"],
        "contentRootSha256": manifest["content_root_sha256"],
        "sourceCommit": manifest["source_commit"],
        "offlinePackDeclared": matrix.get("offline") == "YES",
        **{
            kind: [content_item(pack_dir, path, kind[:-1], number) for number, path in enumerate(kind_paths, 1)]
            for kind, kind_paths in selected.items()
        },
    }


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix_data = json.loads(MATRIX.read_text(encoding="utf-8"))
    matrix = {row["track"]: row for row in matrix_data.get("rows") or []}
    tracks = [build_track(track, matrix[track["track_id"]]) for track in registry.get("tracks") or []]
    if len(tracks) != 18:
        raise RuntimeError(f"public content track count {len(tracks)} != 18")
    payload = {
        "schema": "waike.public_curriculum_content.v1",
        "sourceCommit": tracks[0]["sourceCommit"],
        "trackCount": len(tracks),
        "tracks": tracks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "tracks": len(tracks), "output": str(OUTPUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
