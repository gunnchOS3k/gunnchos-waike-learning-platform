"""AI grade safety: suggestions only; never silent grade mutation."""

from helpers import SECTION, auth_header, login


def test_instructor_assist_is_suggestion_only(client):
    instructor = login(client, "instructor-alpha")
    r = client.post(
        "/api/v1/ai/instructor/assist",
        headers=auth_header(instructor["token"]),
        json={
            "section_id": SECTION,
            "capability": "feedback_suggest",
            "query": "Suggest feedback for conceptual understanding",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggestion_only"] is True
    assert body["mutates_grades"] is False
    assert body["hitl_required"] is True


def test_ai_apply_grade_always_forbidden(client):
    instructor = login(client, "instructor-alpha")
    r = client.post(
        "/api/v1/ai/instructor/apply-grade",
        headers=auth_header(instructor["token"]),
        json={
            "section_id": SECTION,
            "submission_id": "sub_anything",
            "points": 100,
            "explicit_confirm": True,
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "AI_SILENT_GRADE_FORBIDDEN"


def test_learner_cannot_apply_grade_via_ai(client):
    learner = login(client, "learner-alpha")
    r = client.post(
        "/api/v1/ai/instructor/apply-grade",
        headers=auth_header(learner["token"]),
        json={"submission_id": "sub_x", "points": 99, "explicit_confirm": True},
    )
    assert r.status_code == 403


def test_grading_triage_does_not_write_gradebook(client, prod_app):
    instructor = login(client, "instructor-alpha")
    before = prod_app.state.db.execute("SELECT COUNT(*) AS c FROM grades").fetchone()
    r = client.post(
        "/api/v1/ai/instructor/assist",
        headers=auth_header(instructor["token"]),
        json={
            "section_id": SECTION,
            "capability": "grading_triage",
            "query": "Triage ungraded submissions",
            "instructor_context": {"answer_key": "not_for_learners"},
        },
    )
    assert r.status_code == 200
    after = prod_app.state.db.execute("SELECT COUNT(*) AS c FROM grades").fetchone()
    assert after["c"] == before["c"]
    assert r.json()["mutates_grades"] is False
