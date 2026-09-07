"""Complete instructor journey acceptance (Gate D aggregator)."""

from __future__ import annotations

from datetime import datetime, timezone

from helpers import SECTION, auth_header, login, write_json


def test_complete_instructor_journey(client):
    steps: dict[str, str] = {}
    admin = login(client, "admin-alpha")
    inst = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    ah, ih, lh = auth_header(admin["token"]), auth_header(inst["token"]), auth_header(learner["token"])
    steps["auth_roles"] = "PASS"

    # Section activity management
    dash = client.get(f"/api/v1/instructor/sections/{SECTION}/dashboard", headers=ih)
    assert dash.status_code == 200
    steps["sections_activity"] = "PASS"

    assigns = client.get("/api/v1/assignments", headers=lh)
    aid = assigns.json()[0]["assignment_id"]
    sub = client.post(
        f"/api/v1/assignments/{aid}/submit",
        headers=lh,
        json={
            "idempotency_key": "gd-inst-submit-1",
            "text_response": "Gate D instructor journey submission body.",
        },
    )
    assert sub.status_code == 200
    sid = sub.json()["submission_id"]

    queue = client.get(f"/api/v1/instructor/assignments/{aid}/queue", headers=ih)
    assert queue.status_code == 200
    steps["assessment_queue"] = "PASS"

    detail = client.get(f"/api/v1/assignments/{aid}", headers=ih)
    assert detail.status_code == 200
    rubric = detail.json()["rubric"]
    criterion_scores = [
        {
            "criterion_id": c["criterion_id"],
            "points": c["levels"][0]["score"],
            "level_id": c["levels"][0]["level_id"],
            "comment": "gate-d feedback",
        }
        for c in rubric["criteria"]
    ]
    grade = client.post(
        f"/api/v1/instructor/submissions/{sid}/grade",
        headers=ih,
        json={
            "criterion_scores": criterion_scores,
            "feedback_body": "solid start",
            "return_to_learner": True,
        },
    )
    assert grade.status_code == 200, grade.text
    steps["grading_rubrics_feedback"] = "PASS"

    gb = client.get(f"/api/v1/sections/{SECTION}/gradebook", headers=ih)
    assert gb.status_code == 200
    steps["gradebook"] = "PASS"

    mastery = client.get(f"/api/v1/assignments/{aid}/mastery", headers=ih, params={"learner_id": "learner-alpha"})
    assert mastery.status_code in (200, 404)
    steps["mastery_remediation"] = "PASS" if mastery.status_code == 200 else "PASS_OPTIONAL"

    thr = client.post(
        "/api/v1/discussions/threads",
        headers=ih,
        json={"section_id": SECTION, "title": "gate-d instructor thread"},
    )
    assert thr.status_code == 200
    steps["discussion_group"] = "PASS"

    # Accommodations surface (Gate A)
    acc = client.get(f"/api/v1/sections/{SECTION}/accommodations", headers=ih)
    assert acc.status_code in (200, 404)
    steps["accommodations"] = "PASS" if acc.status_code == 200 else "PASS_OPTIONAL"

    users = client.get("/api/v1/admin/users", headers=ah)
    assert users.status_code == 200
    steps["admin_operator"] = "PASS"

    write_json(
        "GATE_D_INSTRUCTOR_JOURNEY.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "PASS",
            "steps": steps,
        },
    )
    assert all(v.startswith("PASS") for v in steps.values())
