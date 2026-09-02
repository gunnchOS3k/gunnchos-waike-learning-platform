"""JSON Schema validation against contracts/schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .compat import CompatDecision, RejectionReason, check_schema_version
from .registry import repo_root


SCHEMA_MAP = {
    "canonical_track_reference": "canonical_track_reference.v1.json",
    "course_module": "course_module.v1.json",
    "learner_pack_manifest": "learner_pack_manifest.v1.json",
    "instructor_pack_manifest": "instructor_pack_manifest.v1.json",
    "assessment": "assessment.v1.json",
    "rubric": "rubric.v1.json",
    "lab_environment": "lab_environment.v1.json",
    "compatibility_manifest": "compatibility_manifest.v1.json",
    "package_signature_metadata": "package_signature_metadata.v1.json",
}


def schema_path(name: str) -> Path:
    return repo_root() / "contracts" / "schemas" / SCHEMA_MAP[name]


def load_schema(name: str) -> dict[str, Any]:
    return json.loads(schema_path(name).read_text(encoding="utf-8"))


def validate_document(name: str, doc: dict[str, Any]) -> CompatDecision:
    sv = doc.get("schema_version", "0.0.0")
    decision = check_schema_version(name, sv)
    if not decision.ok:
        return decision
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        return CompatDecision(
            False,
            RejectionReason.INCOMPATIBLE_SCHEMA_MAJOR,
            "; ".join(e.message for e in errors[:5]),
        )
    return CompatDecision(True)
