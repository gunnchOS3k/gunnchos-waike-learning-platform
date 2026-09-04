"""Client↔hub HTTP seam — same paths/headers as apps/client createHttpHubClient.

Proves the TypeScript HubClient contract agrees with the real hub (isolated local hub).
"""

from __future__ import annotations

import json
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
def hub(tmp_path, monkeypatch):
    waike = _waike()
    monkeypatch.setenv("WAIKE_ROOT", str(waike))
    db = tmp_path / "http_seam.sqlite3"
    app = create_app(HubConfig(), db_path=db, seed=True)
    return TestClient(app)


class HttpHubClient:
    """Python mirror of apps/client/src/lib/hub/client.ts createHttpHubClient."""

    def __init__(self, client: TestClient, actor_id: str, role: str):
        self.client = client
        self.headers = {
            "Content-Type": "application/json",
            "X-Waike-Actor-Id": actor_id,
            "X-Waike-Actor-Role": role,
        }

    def list_assignments(self):
        r = self.client.get("/api/v1/assignments", headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def get_assignment(self, assignment_id: str):
        r = self.client.get(f"/api/v1/assignments/{assignment_id}", headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def save_draft(self, assignment_id: str, text: str):
        r = self.client.put(
            f"/api/v1/assignments/{assignment_id}/draft",
            headers=self.headers,
            json={"text_response": text, "artifact_name": None, "artifact_base64": None},
        )
        assert r.status_code == 200, r.text
        return r.json()

    def submit(self, assignment_id: str, idempotency_key: str, text: str | None = None):
        r = self.client.post(
            f"/api/v1/assignments/{assignment_id}/submit",
            headers=self.headers,
            json={"idempotency_key": idempotency_key, "text_response": text},
        )
        assert r.status_code == 200, r.text
        return r.json()

    def queue(self, assignment_id: str):
        r = self.client.get(
            f"/api/v1/instructor/assignments/{assignment_id}/queue",
            headers=self.headers,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def grade(self, submission_id: str, body: dict):
        r = self.client.post(
            f"/api/v1/instructor/submissions/{submission_id}/grade",
            headers=self.headers,
            content=json.dumps({**body, "return_to_learner": True}),
        )
        assert r.status_code == 200, r.text
        return r.json()

    def get_submission(self, submission_id: str):
        r = self.client.get(f"/api/v1/submissions/{submission_id}", headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()


def test_http_client_real_hub_assignment_draft_submit_grade_feedback(hub):
    learner = HttpHubClient(hub, "learner-a", "learner")
    instructor = HttpHubClient(hub, "instructor-1", "instructor")

    # HTTP client lists real WAIKE assignment
    listed = learner.list_assignments()
    assert any(a["assignment_id"] == ASSIGNMENT_ID for a in listed)
    detail = learner.get_assignment(ASSIGNMENT_ID)
    assert detail["title"] == "Mental model reflection"
    assert detail["source_path"].endswith("week_01.yaml")
    assert len(detail["rubric"]["criteria"]) >= 5

    # Saves draft via HTTP
    draft = learner.save_draft(ASSIGNMENT_ID, "HTTP seam draft on real DIGITAL_CONFIDENCE.")
    assert draft["revision"] >= 1
    assert "HTTP seam draft" in draft["text_response"]

    # Submits via HTTP
    sub = learner.submit(ASSIGNMENT_ID, "idem-http-seam-1", "Final HTTP seam reflection.")
    assert sub["status"] == "submitted"
    assert sub["receipt"]["content_hash"] == sub["content_hash"]
    submission_id = sub["submission_id"]

    # Instructor HTTP client sees it and grades
    queue = instructor.queue(ASSIGNMENT_ID)
    assert any(q["submission_id"] == submission_id for q in queue)
    scores = []
    for c in detail["rubric"]["criteria"]:
        level = next(l for l in c["levels"] if float(l["score"]) == 2.0)
        scores.append(
            {
                "criterion_id": c["criterion_id"],
                "points": 2.0,
                "level_id": level["level_id"],
                "comment": "http seam",
            }
        )
    graded = instructor.grade(
        submission_id,
        {"criterion_scores": scores, "feedback_body": "HTTP seam feedback — develop further."},
    )
    assert graded["grade"]["returned"] == 1
    assert graded["mastery"]["mastered"] == 0
    assert graded["remediation"]["status"] == "assigned"

    # Learner HTTP client gets returned grade/feedback
    view = learner.get_submission(submission_id)
    assert view["grade"] is not None
    assert view["grade"]["points_earned"] == 10.0  # 5 criteria × 2
    assert view["grade"]["points_possible"] == 20.0  # 5 × 4
    assert any("HTTP seam feedback" in f["body"] for f in view["feedback"])
    assert len(view["evaluations"]) == len(detail["rubric"]["criteria"])
