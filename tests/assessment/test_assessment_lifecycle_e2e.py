"""PR2 assessment lifecycle — 15 automated acceptance steps + auth negatives.

Uses real WAIKE DIGITAL_CONFIDENCE assignment digital_confidence_w01.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import HubConfig, create_app

ROOT = Path(__file__).resolve().parents[2]
WAIKE = ROOT.parent / "waike-research-ops"
ASSIGNMENT_ID = "digital_confidence_w01"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    assert WAIKE.is_dir(), f"WAIKE SoT missing at {WAIKE}"
    assign = WAIKE / "assignments/by_course/digital_confidence/week_01.yaml"
    assert assign.is_file(), "real DIGITAL_CONFIDENCE week_01 assignment required"
    monkeypatch.setenv("WAIKE_ROOT", str(WAIKE))
    db = tmp_path / "assessment.sqlite3"
    app = create_app(HubConfig(), db_path=db, seed=True)
    return TestClient(app)


def H(actor: str, role: str) -> dict[str, str]:
    return {"X-Waike-Actor-Id": actor, "X-Waike-Actor-Role": role}


LEARNER = H("learner-a", "learner")
LEARNER_B = H("learner-b", "learner")
INSTRUCTOR = H("instructor-1", "instructor")


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


def test_assessment_lifecycle_fifteen_steps(client):
    steps: dict[str, bool] = {}

    # 1. learner sees assignment (real WAIKE DIGITAL_CONFIDENCE)
    r = client.get("/api/v1/assignments", headers=LEARNER)
    assert r.status_code == 200
    assignments = r.json()
    assert any(a["assignment_id"] == ASSIGNMENT_ID for a in assignments)
    detail = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}", headers=LEARNER)
    assert detail.status_code == 200
    assignment = detail.json()
    assert assignment["title"] == "Mental model reflection"
    assert "digital confidence" in assignment["body_markdown"].lower() or "Devices" in assignment["body_markdown"]
    assert assignment["source_path"].endswith("week_01.yaml")
    assert len(assignment["rubric"]["criteria"]) >= 5
    steps["1_learner_sees_assignment"] = True

    # 2. drafts + artifact
    art = base64.b64encode(b"diagram-bytes-fixture").decode()
    draft = client.put(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/draft",
        headers=LEARNER,
        json={
            "text_response": "Draft reflection on digital confidence in my community.",
            "artifact_name": "mental_model.png",
            "artifact_base64": art,
        },
    )
    assert draft.status_code == 200
    assert draft.json()["revision"] == 1
    assert draft.json()["artifact_name"] == "mental_model.png"
    steps["2_drafts"] = True

    # 3. restart preserves draft (new client, same DB)
    db_path = Path(client.app.state.db_path)
    client2 = TestClient(create_app(HubConfig(), db_path=db_path, seed=True))
    resumed = client2.get(f"/api/v1/assignments/{ASSIGNMENT_ID}/draft", headers=LEARNER)
    assert resumed.status_code == 200
    assert "Draft reflection" in resumed.json()["text_response"]
    assert resumed.json()["artifact_sha256"]
    steps["3_restart_preserves_draft"] = True
    # continue with client2 as primary after "restart"
    client = client2

    # 4. submits
    submit = client.post(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/submit",
        headers=LEARNER,
        json={
            "idempotency_key": "idem-learner-a-attempt-1",
            "text_response": "Final reflection on digital confidence — community mental model.",
        },
    )
    assert submit.status_code == 200
    sub = submit.json()
    assert sub["status"] == "submitted"
    assert sub["receipt"]["content_hash"] == sub["content_hash"]
    assert sub["attempt_number"] == 1
    assert len(sub["artifacts"]) == 1
    submission_id = sub["submission_id"]
    steps["4_submits"] = True

    # 5. duplicate retry does not duplicate submission
    retry = client.post(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/submit",
        headers=LEARNER,
        json={
            "idempotency_key": "idem-learner-a-attempt-1",
            "text_response": "Final reflection on digital confidence — community mental model.",
        },
    )
    assert retry.status_code == 200
    assert retry.json()["submission_id"] == submission_id
    hist = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}/history", headers=LEARNER)
    assert hist.status_code == 200
    assert len(hist.json()) == 1
    steps["5_idempotent_submit"] = True

    # 6. instructor sees submission
    queue = client.get(f"/api/v1/instructor/assignments/{ASSIGNMENT_ID}/queue", headers=INSTRUCTOR)
    assert queue.status_code == 200
    assert any(q["submission_id"] == submission_id for q in queue.json())
    view = client.get(f"/api/v1/submissions/{submission_id}", headers=INSTRUCTOR)
    assert view.status_code == 200
    assert view.json()["learner_id"] == "learner-a"
    steps["6_instructor_sees_submission"] = True

    # 7. instructor grades by rubric (force mastery gap for remediation path)
    grade1 = client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=INSTRUCTOR,
        json={
            "criterion_scores": _criteria_scores(assignment, 2.0),
            "feedback_body": "Developing — strengthen documentation and conceptual depth.",
            "return_to_learner": True,
            "force_mastery_gap": True,
        },
    )
    assert grade1.status_code == 200
    g1 = grade1.json()
    assert g1["grade"]["returned"] == 1
    assert g1["mastery"]["mastered"] == 0
    assert g1["remediation"]["status"] == "assigned"
    assert g1["portfolio"] is None
    grade_id = g1["grade"]["grade_id"]
    steps["7_instructor_grades_rubric"] = True

    # 8. learner receives grade/feedback
    learner_view = client.get(f"/api/v1/submissions/{submission_id}", headers=LEARNER)
    assert learner_view.status_code == 200
    lv = learner_view.json()
    assert lv["grade"] is not None
    assert lv["grade"]["points_earned"] > 0
    assert any("Developing" in f["body"] for f in lv["feedback"])
    assert lv["evaluations"]
    gb = client.get("/api/v1/gradebook", headers=LEARNER)
    assert gb.status_code == 200
    assert any(e["assignment_id"] == ASSIGNMENT_ID for e in gb.json())
    steps["8_learner_receives_grade_feedback"] = True

    # 9. mastery gap generated
    mastery = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}/mastery", headers=LEARNER)
    assert mastery.status_code == 200
    assert mastery.json()["mastered"] == 0
    assert mastery.json()["gap_notes"]
    steps["9_mastery_gap"] = True

    # 10. remediation assigned
    rem = client.get("/api/v1/remediation", headers=LEARNER)
    assert rem.status_code == 200
    assert any(p["assignment_id"] == ASSIGNMENT_ID and p["status"] == "assigned" for p in rem.json())
    steps["10_remediation_assigned"] = True

    # 11. learner resubmits
    resub = client.post(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/submit",
        headers=LEARNER,
        json={
            "idempotency_key": "idem-learner-a-attempt-2",
            "text_response": "Revised reflection after remediation — clearer mental model and evidence.",
            "artifact_name": "mental_model_v2.png",
            "artifact_base64": base64.b64encode(b"revised-diagram").decode(),
        },
    )
    assert resub.status_code == 200
    sub2 = resub.json()
    assert sub2["attempt_number"] == 2
    assert sub2["submission_id"] != submission_id
    hist2 = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}/history", headers=LEARNER)
    assert len(hist2.json()) == 2
    steps["11_learner_resubmits"] = True

    # 12. instructor regrades
    grade2 = client.post(
        f"/api/v1/instructor/submissions/{sub2['submission_id']}/grade",
        headers=INSTRUCTOR,
        json={
            "criterion_scores": _criteria_scores(assignment, 4.0),
            "feedback_body": "Excellent revision — portfolio ready.",
            "return_to_learner": True,
            "force_mastery_gap": False,
        },
    )
    assert grade2.status_code == 200
    g2 = grade2.json()
    assert g2["mastery"]["mastered"] == 1
    audit = client.get(f"/api/v1/instructor/grades/{grade_id}/audit", headers=INSTRUCTOR)
    assert audit.status_code == 200
    assert len(audit.json()) >= 1
    # also revise original grade to prove audit revision path
    revise = client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=INSTRUCTOR,
        json={
            "criterion_scores": _criteria_scores(assignment, 2.0),
            "feedback_body": "Historical attempt remains developing.",
            "return_to_learner": True,
            "force_mastery_gap": True,
        },
    )
    assert revise.status_code == 200
    assert revise.json()["grade"]["revision"] >= 2
    audit2 = client.get(f"/api/v1/instructor/grades/{grade_id}/audit", headers=INSTRUCTOR)
    assert len(audit2.json()) >= 2
    steps["12_instructor_regrades"] = True

    # 13. mastery updates
    mastery2 = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}/mastery", headers=LEARNER)
    assert mastery2.status_code == 200
    assert mastery2.json()["mastered"] == 1
    assert mastery2.json()["submission_id"] == sub2["submission_id"]
    steps["13_mastery_updates"] = True

    # 14. portfolio evidence created
    assert g2["portfolio"] is not None
    port = client.get("/api/v1/portfolio", headers=LEARNER)
    assert port.status_code == 200
    assert any(p["submission_id"] == sub2["submission_id"] for p in port.json())
    rem_after = client.get("/api/v1/remediation", headers=LEARNER)
    assert any(p["status"] == "completed" for p in rem_after.json())
    steps["14_portfolio_evidence"] = True

    # 15. unauthorized access negatives fail server-side
    # other learner cannot read submission
    deny = client.get(f"/api/v1/submissions/{submission_id}", headers=LEARNER_B)
    assert deny.status_code == 403
    assert deny.json()["detail"] == "FORBIDDEN_OTHER_LEARNER"
    # learner cannot access instructor queue
    deny_q = client.get(f"/api/v1/instructor/assignments/{ASSIGNMENT_ID}/queue", headers=LEARNER)
    assert deny_q.status_code == 403
    # learner cannot grade
    deny_g = client.post(
        f"/api/v1/instructor/submissions/{submission_id}/grade",
        headers=LEARNER,
        json={"criterion_scores": _criteria_scores(assignment, 4.0), "feedback_body": "nope"},
    )
    assert deny_g.status_code == 403
    # learner cannot read other learner portfolio
    deny_p = client.get("/api/v1/portfolio", headers=LEARNER, params={"learner_id": "learner-b"})
    assert deny_p.status_code == 403
    # role mismatch header
    bad = client.get(
        "/api/v1/assignments",
        headers={"X-Waike-Actor-Id": "learner-a", "X-Waike-Actor-Role": "instructor"},
    )
    assert bad.status_code == 403
    assert bad.json()["detail"] == "ROLE_MISMATCH"
    # instructor cannot be used as learner draft endpoint successfully with learner role check
    # (instructor role rejected by require_learner)
    deny_draft = client.put(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/draft",
        headers=INSTRUCTOR,
        json={"text_response": "should fail"},
    )
    assert deny_draft.status_code == 403
    steps["15_unauthorized_negatives"] = True

    assert all(steps.values()), json.dumps(steps, indent=2)
    assert len(steps) == 15


def test_receipt_immutable_payload(client):
    detail = client.get(f"/api/v1/assignments/{ASSIGNMENT_ID}", headers=LEARNER).json()
    assert detail["assignment_id"] == ASSIGNMENT_ID
    sub = client.post(
        f"/api/v1/assignments/{ASSIGNMENT_ID}/submit",
        headers=LEARNER,
        json={"idempotency_key": "idem-receipt", "text_response": "Receipt fixture reflection."},
    ).json()
    rcpt = client.get(f"/api/v1/submissions/{sub['submission_id']}/receipt", headers=LEARNER)
    assert rcpt.status_code == 200
    payload = json.loads(rcpt.json()["immutable_payload"])
    assert payload["content_hash"] == sub["content_hash"]
    assert payload["submission_id"] == sub["submission_id"]
