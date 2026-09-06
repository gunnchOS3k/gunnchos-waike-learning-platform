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
    """PR2 regression fixture-auth client."""
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "hub.sqlite3"
    app = create_app(
        config=HubConfig(
            fixture_auth_enabled=True,
            production_auth_enabled=False,
            learner_data_enabled=True,
            database={"enabled": True, "url": str(db), "note": "test"},
        ),
        db_path=db,
        seed=True,
    )
    return TestClient(app)


@pytest.fixture()
def prod_client(tmp_path, monkeypatch):
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "hub_prod.sqlite3"
    app = create_app(
        config=HubConfig(
            fixture_auth_enabled=False,
            production_auth_enabled=True,
            learner_data_enabled=True,
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


def test_version_fixture_mode_for_pr2_regression(client):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["fixture_auth_enabled"] is True
    assert body["production_auth_enabled"] is False
    assert body["learner_data_enabled"] is True
    assert body["assessment_lifecycle"] is True
    assert body["identity"] is True
    assert (
        "pr3" in body["version"]
        or "pr2" in body["version"]
        or "gate-a" in body["version"]
        or body["version"].startswith("0.3")
        or body["version"].startswith("0.4")
    )
    assert body.get("offline_sync") is True or "gate-a" in body["version"] or "pr3" in body["version"]


def test_version_production_defaults(prod_client):
    body = prod_client.get("/version").json()
    assert body["production_auth_enabled"] is True
    assert body["fixture_auth_enabled"] is False
    assert body["gradebook"] is True


def test_config_db_enabled(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body["database"]["enabled"] is True
    assert body["fixture_auth_enabled"] is True
    assert body["production_auth_enabled"] is False


def test_auth_required(client):
    r = client.get("/api/v1/assignments")
    assert r.status_code == 401
    assert r.json()["detail"] == "AUTH_REQUIRED"


def test_fixture_headers_rejected_in_production(prod_client):
    r = prod_client.get(
        "/api/v1/assignments",
        headers={"X-Waike-Actor-Id": "learner-a", "X-Waike-Actor-Role": "learner"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "FIXTURE_AUTH_REJECTED"
