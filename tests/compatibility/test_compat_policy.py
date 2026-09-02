"""Contract schema validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"


def load_schema(name: str):
    return json.loads((SCHEMAS / name).read_text())


@pytest.mark.parametrize(
    "name",
    [
        "canonical_track_reference.v1.json",
        "course_module.v1.json",
        "learner_pack_manifest.v1.json",
        "instructor_pack_manifest.v1.json",
        "assessment.v1.json",
        "rubric.v1.json",
        "lab_environment.v1.json",
        "compatibility_manifest.v1.json",
        "package_signature_metadata.v1.json",
    ],
)
def test_schema_is_draft_2020_12(name):
    schema = load_schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_valid_track_fixture():
    schema = load_schema("canonical_track_reference.v1.json")
    instance = {
        "schema_version": "1.0.0",
        "track_id": "DIGITAL_CONFIDENCE",
        "title": "Digital Confidence to Computer Operator",
        "academy_id": "ACADEMY_IT",
    }
    Draft202012Validator(schema).validate(instance)


def test_rejects_wrong_schema_version_const():
    schema = load_schema("canonical_track_reference.v1.json")
    instance = {
        "schema_version": "9.0.0",
        "track_id": "X",
        "title": "X",
        "academy_id": "A",
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(instance)
