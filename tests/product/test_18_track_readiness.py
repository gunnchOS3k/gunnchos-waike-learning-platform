from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_registry_has_18_import_manifests() -> None:
    imports = ROOT / "curriculum" / "imports"
    files = sorted(p.name for p in imports.glob("*.import.json"))
    assert len(files) == 18


def test_readiness_report_complete_and_no_invented_sot() -> None:
    report = json.loads((ROOT / "artifacts" / "curriculum" / "WAIKE_18_TRACK_LEARNER_READINESS.json").read_text())
    assert report["invented_content"] is False
    assert report["human_review_claimed"] is False
    assert len(report["tracks"]) == 18
    for row in report["tracks"]:
        assert row["status"] in {"READY", "PARTIAL", "BLOCKED_AUTHORING", "BLOCKED_HUMAN_REVIEW"}
        assert row["invented_content"] is False


def test_no_duplicate_curriculum_sot_in_client() -> None:
    client = ROOT / "apps" / "client" / "src"
    banned = list(client.rglob("*curriculum*sot*"))
    assert banned == []
