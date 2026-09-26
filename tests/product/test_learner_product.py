from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import HubConfig, create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        config=HubConfig(fixture_auth_enabled=True, production_auth_enabled=False, environment="test"),
        db_path=tmp_path / "hub.sqlite3",
        seed=True,
    )
    return TestClient(app)


def test_search_and_mlv_are_authenticated_and_user_scoped(tmp_path: Path) -> None:
    client = _client(tmp_path)
    denied = client.get("/api/v1/learner/search", params={"q": "digital"})
    assert denied.status_code == 401
    home = client.get("/api/v1/learner/search", params={"q": "digital"}, headers={"X-Waike-Actor-Id": "learner-a", "X-Waike-Actor-Role": "learner"})
    assert home.status_code == 200
    blob = str(home.json()).lower()
    assert "answer key" not in blob
    mlv = client.get("/api/v1/mlv/consumer-summary", headers={"X-Waike-Actor-Id": "learner-a", "X-Waike-Actor-Role": "learner"})
    assert mlv.status_code == 200
    body = mlv.json()
    assert body["contract"] == "WAIKE_MLV_EDUCATION_CONTRACT.v1"
    assert "answer_key" not in str(body).lower()


def test_due_shift_preview_and_comment_bank(tmp_path: Path) -> None:
    client = _client(tmp_path)
    headers = {"X-Waike-Actor-Id": "instructor-1", "X-Waike-Actor-Role": "instructor"}
    preview = client.get(
        "/api/v1/instructor/sections/sec_alpha_dc_w01/due-shift/preview",
        params={"hours": 24},
        headers=headers,
    )
    assert preview.status_code == 200
    saved = client.post("/api/v1/instructor/comment-bank", json={"title": "Nice", "body": "Clear example"}, headers=headers)
    assert saved.status_code == 200
    listed = client.get("/api/v1/instructor/comment-bank", headers=headers)
    assert any(row["title"] == "Nice" for row in listed.json())


def test_school_apps_empty_without_institution_config(tmp_path: Path) -> None:
    client = _client(tmp_path)
    apps = client.get("/api/v1/school-apps", headers={"X-Waike-Actor-Id": "learner-a", "X-Waike-Actor-Role": "learner"})
    assert apps.status_code == 200
    assert apps.json() == []
