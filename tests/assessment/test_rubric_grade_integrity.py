"""Rubric-grade integrity — fail-closed negatives + no partial eval mutation."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import HubConfig, create_app

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENT_ID = "digital_confidence_w01"


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
    raise FileNotFoundError("waike-research-ops missing")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "rubric.sqlite3"
    return TestClient(create_app(HubConfig(), db_path=db, seed=True))


def H(actor: str, role: str) -> dict[str, str]:
    return {"X-Waike-Actor-Id": actor, "X-Waike-Actor-Role": role}


LEARNER = H("learner-a", "learner")
INSTRUCTOR = H("instructor-1", "instructor")


def _assignment(client) -> dict:
    return client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}", headers=LEARNER).json()


def _criteria_scores(assignment: dict, points: float) -> list[dict]:
    scores = []
    for c in assignment["rubric"]["criteria"]:
        level = next((l for l in c["levels"] if float(l["score"]) == float(points)), c["levels"][0])
        scores.append(
            {
                "criterion_id": c["criterion_id"],
                "points": float(points),
                "level_id": level["level_id"],
                "comment": f"scored {points}",
            }
        )
    return scores


def _submit(client, key: str = "idem-rubric-neg") -> str:
    sub = client.post(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/submit",
        headers=LEARNER,
        json={"idempotency_key": key, "text_response": "Rubric integrity fixture."},
    )
    assert sub.status_code == 200
    return sub.json()["submission_id"]


def _grade(client, submission_id: str, scores: list[dict]):
    return client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=INSTRUCTOR,
        json={"criterion_scores": scores, "feedback_body": "check", "return_to_learner": True},
    )


def test_negative_points_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "neg-points")
    scores = _criteria_scores(assignment, 2.0)
    scores[0]["points"] = -1.0
    scores[0]["level_id"] = None
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "POINTS_OUT_OF_RANGE"


def test_points_above_max_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "above-max")
    scores = _criteria_scores(assignment, 2.0)
    scores[0]["points"] = 99.0
    scores[0]["level_id"] = None
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "POINTS_OUT_OF_RANGE"


def test_duplicate_criterion_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "dup-crit")
    scores = _criteria_scores(assignment, 2.0)
    scores.append(dict(scores[0]))
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "DUPLICATE_CRITERION"


def test_missing_required_criterion_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "missing-crit")
    scores = _criteria_scores(assignment, 2.0)[1:]  # drop first
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "MISSING_REQUIRED_CRITERIA"


def test_empty_criterion_list_rejected(client):
    sid = _submit(client, "empty-list")
    r = _grade(client, sid, [])
    assert r.status_code == 400
    # pydantic may 422 on empty depending on model; service also rejects
    assert r.status_code in (400, 422)
    if r.status_code == 400:
        assert r.json()["detail"] == "EMPTY_CRITERION_SCORES"


def test_invalid_level_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "bad-level")
    scores = _criteria_scores(assignment, 2.0)
    scores[0]["level_id"] = "level_does_not_exist"
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "INVALID_LEVEL"


def test_level_from_other_criterion_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "cross-level")
    scores = _criteria_scores(assignment, 2.0)
    # Swap level from second criterion onto first
    scores[0]["level_id"] = scores[1]["level_id"]
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "LEVEL_CRITERION_MISMATCH"


def test_mismatched_level_points_rejected(client):
    assignment = _assignment(client)
    sid = _submit(client, "level-pts-mismatch")
    scores = _criteria_scores(assignment, 2.0)
    # Keep L2 level_id but claim 4 points
    scores[0]["points"] = 4.0
    r = _grade(client, sid, scores)
    assert r.status_code == 400
    assert r.json()["detail"] == "LEVEL_POINTS_MISMATCH"


def test_failed_regrade_preserves_existing_evaluations(client):
    assignment = _assignment(client)
    sid = _submit(client, "preserve-evals")
    ok = _grade(client, sid, _criteria_scores(assignment, 2.0))
    assert ok.status_code == 200
    before = client.get(f"/api/v1/submissions/{sid}", headers=INSTRUCTOR).json()["evaluations"]
    assert len(before) == len(assignment["rubric"]["criteria"])

    bad_scores = _criteria_scores(assignment, 2.0)
    bad_scores[0]["points"] = -5.0
    bad_scores[0]["level_id"] = None
    bad = _grade(client, sid, bad_scores)
    assert bad.status_code == 400

    after = client.get(f"/api/v1/submissions/{sid}", headers=INSTRUCTOR).json()["evaluations"]
    assert after == before


def test_full_grade_points_possible_is_entire_rubric(client):
    assignment = _assignment(client)
    sid = _submit(client, "full-possible")
    scores = _criteria_scores(assignment, 3.0)
    r = _grade(client, sid, scores)
    assert r.status_code == 200
    expected_possible = sum(float(c["max_points"]) for c in assignment["rubric"]["criteria"])
    assert r.json()["grade"]["points_possible"] == expected_possible
    assert r.json()["mastery"]["mastered"] == 1  # avg 3.0 == threshold
