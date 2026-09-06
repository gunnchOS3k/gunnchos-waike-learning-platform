"""Adversarial sabotage: authz, lease, answer-key, hardware, enrollment revoke."""

from helpers import SECTION, auth_header, login, user_id


def test_disabled_user_and_enrollment_revoke(client, prod_app):
    admin = login(client, "admin-alpha")
    learner = login(client, "learner-alpha")
    h = auth_header(learner["token"])
    lease = client.post(
        "/api/v1/sync/leases",
        headers=h,
        json={"section_id": SECTION, "device_id": "adv"},
    ).json()
    # Revoke enrollment
    enr = prod_app.state.db.execute(
        "SELECT enrollment_id FROM enrollments WHERE user_id=? AND section_id=? AND status='active'",
        (user_id(learner), SECTION),
    ).fetchone()
    client.post(
        f"/api/v1/admin/enrollments/{enr['enrollment_id']}/deactivate",
        headers=auth_header(admin["token"]),
    )
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": "mut_enroll_revoked01",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "adv",
            "entity_type": "lesson_progress",
            "entity_id": "x",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "p", "lesson_id": "x", "percent_complete": 1},
            "lease_id": lease["lease_id"],
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] in {"ENROLLMENT_REVOKED", "ENROLLMENT_REQUIRED"}


def test_learner_cannot_post_authoritative_grade(client):
    learner = login(client, "learner-alpha")
    # No endpoint for learner to set quiz score directly — manual-grade requires instructor
    start = client.post(
        "/api/v1/quizzes/quiz_dc_w01_gate_a/attempts",
        headers=auth_header(learner["token"]),
    )
    aid = start.json()["attempt_id"]
    client.post(
        f"/api/v1/quiz-attempts/{aid}/submit",
        headers=auth_header(learner["token"]),
        json={"responses": {"qi_file": {}}, "client_mutation_id": "mut_adv_grade_01"},
    )
    r = client.post(
        f"/api/v1/quiz-attempts/{aid}/manual-grade",
        headers=auth_header(learner["token"]),
        json={"item_id": "qi_file", "points": 99},
    )
    assert r.status_code == 403
