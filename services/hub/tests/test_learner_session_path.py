import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import HubConfig, create_app

ROOT = Path(os.environ["WAIKE_ROOT"])
GUNNCHAI = Path(os.environ["GUNNCHAI_ROOT"])
SECTION = "sec_alpha_dc_w01"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WAIKE_ENV", "test")
    monkeypatch.setenv("WAIKE_ROOT", str(ROOT))
    monkeypatch.setenv("GUNNCHAI_ROOT", str(GUNNCHAI))
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    app = create_app(
        HubConfig(fixture_auth_enabled=True, production_auth_enabled=False),
        db_path=tmp_path / "session.db",
        seed=True,
    )
    return TestClient(app)


def login(client, username):
    logged = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "WaikeTestPass1!", "site_id": "site-alpha"},
    )
    assert logged.status_code == 200, logged.text
    return {"Authorization": "Bearer " + logged.json()["token"]}, logged.json()["user"]["user_id"]


def test_learner_opens_lesson_practices_without_a_grade_and_receives_suggestion_only_tutoring(client):
    learner, learner_id = login(client, "learner-alpha")
    db = client.app.state.db
    before = {
        name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        for name in ("grades", "submissions")
    }
    opened = client.get(f"/api/v1/sections/{SECTION}/lessons/1", headers=learner)
    assert opened.status_code == 200, opened.text
    lesson = opened.json()
    lesson_file = ROOT / "curriculum" / "digital_rc" / "DIGITAL_CONFIDENCE" / "weeks" / "w01" / "lesson.md"
    assert lesson["text"] == lesson_file.read_text(encoding="utf-8")
    assert lesson["grade_written"] is False
    assert lesson["progress_store"] == "lesson_progress"
    progress = db.execute(
        "SELECT percent_complete FROM lesson_progress WHERE user_id=? AND lesson_id=?",
        (learner_id, "w01"),
    ).fetchone()
    assert progress is not None and progress[0] == 1

    quiz_path = ROOT / "curriculum" / "digital_rc" / "GENERAL_IT" / "quizzes" / "q01.json"
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    practical = client.post(
        f"/api/v1/sections/{SECTION}/lessons/1/practice",
        headers=learner,
        json={
            "quiz_sha256": hashlib.sha256(quiz_path.read_bytes()).hexdigest(),
            "responses": {item["id"]: 0 for item in quiz["items"]},
        },
    )
    assert practical.status_code == 200, practical.text
    assert practical.json()["persisted"] is False
    assert practical.json()["grade_written"] is False
    assert practical.json()["kind"] == "formative_practice"

    tutoring = client.post(
        "/api/v1/ai/learner/assist",
        headers=learner,
        json={
            "section_id": SECTION,
            "capability": "explain",
            "query": "kiosk idle essay session",
            "processing_mode": "local-only",
        },
    )
    assert tutoring.status_code == 200, tutoring.text
    body = tutoring.json()
    assert body["suggestion_only"] is True
    assert body["mutates_grades"] is False
    assert body["grounded"] is True
    excerpt = body["text"].split("\n\n", 1)[1]
    assert excerpt in lesson["text"]
    assert "grade" not in body
    assert "completion" not in body
    after = {
        name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        for name in ("grades", "submissions")
    }
    assert after == before
    assert (
        db.execute(
            "SELECT COUNT(*) FROM lesson_progress WHERE user_id=? AND lesson_id=?",
            (learner_id, "w01"),
        ).fetchone()[0]
        == 1
    )
