from fastapi.testclient import TestClient

from app.main import create_app, HubConfig


def test_healthz():
    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_disables_auth_and_learner_data():
    client = TestClient(create_app())
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is False
    assert body["learner_data_enabled"] is False


def test_config_db_placeholder():
    client = TestClient(create_app(HubConfig()))
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body["database"]["enabled"] is False
    assert "NOT enabled" in body["database"]["note"]
