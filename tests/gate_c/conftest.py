"""Gate C pytest fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "services" / "hub"
sys.path.insert(0, str(HUB))

os.environ.setdefault(
    "WAIKE_DEV_DB_KEY",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
)
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
os.environ.setdefault("WAIKE_ALLOW_FAKE_AI", "1")

from app.main import HubConfig, create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path):
    db = tmp_path / "gate_c.sqlite3"
    app = create_app(
        config=HubConfig(fixture_auth_enabled=False, production_auth_enabled=True, environment="test"),
        db_path=db,
        seed=True,
    )
    # Keep backup service path aligned after restores in tests that reopen.
    with TestClient(app) as c:
        c.app.state.db_path = str(db)
        yield c
