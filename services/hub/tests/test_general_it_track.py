"""Second canonical track, in process. No listening Hub."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import HubConfig, create_app

SECTION = "sec_alpha_git_w01"
ASSIGNMENT = "general_it_w01"


def curriculum_root() -> Path:
    candidates = []
    env = os.environ.get("WAIKE_ROOT")
    if env:
        candidates.append(Path(env))
    repos = Path(__file__).resolve().parents[6]
    candidates.append(repos / "_waike_full_delivery" / "curriculum")
    for root in candidates:
        lesson = root / "curriculum" / "digital_rc" / "GENERAL_IT" / "weeks" / "w01" / "lesson.md"
        assign = root / "assignments" / "by_course" / "general_it" / "week_01.yaml"
        quiz = root / "curriculum" / "digital_rc" / "GENERAL_IT" / "quizzes" / "q01.json"
        if lesson.is_file() and assign.is_file() and quiz.is_file():
            return root
    pytest.fail("General IT curriculum is not on disk")


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = curriculum_root()
    monkeypatch.setenv("WAIKE_ENV", "test")
    monkeypatch.setenv("WAIKE_ROOT", str(root))
    monkeypatch.delenv("WAIKE_ALLOW_FAKE_AI", raising=False)
    app = create_app(
        HubConfig(
            fixture_auth_enabled=False,
            production_auth_enabled=True,
            environment="test",
        ),
        db_path=tmp_path / "general-it.db",
        seed=True,
    )
    return TestClient(app)


def login(client, username):
    logged = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "WaikeTestPass1!", "site_id": "site-alpha"},
    )
    assert logged.status_code == 200, logged.text
    return {"Authorization": "Bearer " + logged.json()["token"]}


def grade_rows(client) -> int:
    row = client.app.state.db.execute("SELECT COUNT(*) AS n FROM grades").fetchone()
    return int(row["n"])


def test_general_it_opens_submits_and_grades_without_a_practice_grade(client):
    alpha = login(client, "learner-alpha")
    opened = client.get(f"/api/v1/sections/{SECTION}/lessons/1", headers=alpha)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["grade_written"] is False
    assert "Civic Tech Desk" in body["text"]
    assert body["module_id"] == "GENERAL_IT"

    quiz_path = curriculum_root() / "curriculum" / "digital_rc" / "GENERAL_IT" / "quizzes" / "q01.json"
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    before = grade_rows(client)
    practiced = client.post(
        f"/api/v1/sections/{SECTION}/lessons/1/practice",
        headers=alpha,
        json={
            "quiz_sha256": hashlib.sha256(quiz_path.read_bytes()).hexdigest(),
            "responses": {item["id"]: 0 for item in quiz["items"]},
        },
    )
    assert practiced.status_code == 200, practiced.text
    assert practiced.json()["persisted"] is False
    assert practiced.json()["grade_written"] is False
    assert grade_rows(client) == before

    listed = client.get("/api/v1/assignments", headers=alpha)
    assert listed.status_code == 200, listed.text
    general = next(row for row in listed.json() if row["assignment_id"] == ASSIGNMENT)
    assert general["section_id"] == SECTION
    digital = next(row for row in listed.json() if row["assignment_id"] == "digital_confidence_w01")
    assert digital["section_id"] == "sec_alpha_dc_w01"

    submitted = client.post(
        f"/api/v1/assignments/{ASSIGNMENT}/submit",
        headers=alpha,
        json={
            "idempotency_key": "general-it-alpha-1",
            "text_response": "Alpha General IT evidence for the operator desk.",
            "section_id": SECTION,
        },
    )
    assert submitted.status_code == 200, submitted.text
    submission_id = submitted.json()["submission_id"]

    anonymous = client.post(
        f"/api/v1/assignments/{ASSIGNMENT}/submit",
        json={"idempotency_key": "anon", "text_response": "no", "section_id": SECTION},
    )
    assert anonymous.status_code == 401

    beta = login(client, "learner-beta")
    hidden = client.get(f"/api/v1/submissions/{submission_id}", headers=beta)
    assert hidden.status_code == 403

    instructor = login(client, "instructor-alpha")
    detail = client.get(f"/api/v1/assignments/{ASSIGNMENT}", headers=instructor)
    assert detail.status_code == 200, detail.text
    scores = [
        {"criterion_id": criterion["criterion_id"], "points": 2}
        for criterion in detail.json()["rubric"]["criteria"]
    ]
    graded = client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=instructor,
        json={
            "criterion_scores": scores,
            "feedback_body": "Returned only to the General IT learner.",
            "return_to_learner": True,
        },
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["grade"]["points_earned"] == 10

    visible = client.get(f"/api/v1/submissions/{submission_id}", headers=alpha)
    assert visible.status_code == 200, visible.text
    assert visible.json()["grade"]["points_earned"] == 10
    assert "Returned only to the General IT learner." in json.dumps(visible.json())
    still_hidden = client.get(f"/api/v1/submissions/{submission_id}", headers=beta)
    assert still_hidden.status_code == 403
