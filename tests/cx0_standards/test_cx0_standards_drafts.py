import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "contracts" / "cx0_standards"

REQUIRED = [
    "case_cf_document_v1_draft.json",
    "caliper_envelope_v1_draft.json",
    "open_badge_credential_v1_draft.json",
    "clr_record_v1_draft.json",
    "edu_api_resource_stub_v1_draft.json",
]

def test_draft_schemas_exist_and_forbid_cert_claims():
    for name in REQUIRED:
        data = json.loads((ROOT / name).read_text())
        assert data.get("certification_claimed") is False
        assert "schema" in data
