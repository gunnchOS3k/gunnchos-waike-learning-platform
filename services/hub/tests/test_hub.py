from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import HubConfig, create_app

ROOT = Path(__file__).resolve().parents[3]


def _waike() -> Path:
    import os

    env = os.environ.get("WAIKE_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    nested = ROOT / "waike-research-ops"
    if nested.is_dir():
        return nested
    sibling = ROOT.parent / "waike-research-ops"
    if sibling.is_dir():
        return sibling
    raise FileNotFoundError("waike-research-ops missing for hub tests")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "hub.sqlite3"
    app = create_app(
        config=HubConfig(
            auth_enabled=True,
            learner_data_enabled=True,
            database={"enabled": True, "url": str(db), "note": "test"},
        ),
        db_path=db,
        seed=True,
    )
    return TestClient(app)


def _hdr(actor_id: str, role: str) -> dict[str, str]:
    return {"X-Waike-Actor-Id": actor_id, "X-Waike-Actor-Role": role}


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_enables_pr2_flags(client):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is True
    assert body["learner_data_enabled"] is True
    assert body["assessment_lifecycle"] is True
    assert "pr2" in body["version"]


def test_config_db_enabled(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body["database"]["enabled"] is True


def test_auth_required(client):
    r = client.get("/api/v1/assignments")
    assert r.status_code == 401
    assert r.json()["detail"] == "AUTH_REQUIRED"
