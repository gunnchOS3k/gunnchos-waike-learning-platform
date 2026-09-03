from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]


def test_domain_index_contract():
    schema = json.loads(
        (ROOT / "contracts/schemas/assessment_lifecycle/domain_index.v1.json").read_text()
    )
    fixture = json.loads(
        (ROOT / "contracts/fixtures/assessment/domain_index.valid.json").read_text()
    )
    jsonschema.validate(fixture, schema)
    assert len(fixture["entities"]) == 16


def test_assignment_and_receipt_schemas_load():
    for name in ("assignment.v1.json", "submission_receipt.v1.json"):
        data = json.loads((ROOT / "contracts/schemas/assessment_lifecycle" / name).read_text())
        assert data["$schema"].endswith("2020-12/schema")
