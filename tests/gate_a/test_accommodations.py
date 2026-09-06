"""Accommodations: staff-only, audited, no peer leak, behavioral effect."""

from helpers import SECTION, auth_header, login, user_id


def test_accommodation_attempt_override_and_privacy(client):
    inst = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    peer = login(client, "learner-beta")
    lid = user_id(learner)
    acc = client.post(
        "/api/v1/accommodations",
        headers=auth_header(inst["token"]),
        json={
            "learner_id": lid,
            "section_id": SECTION,
            "attempt_override": 5,
            "time_multiplier": 1.5,
            "notes_private": "IEP confidential",
        },
    )
    assert acc.status_code == 200
    # Peer leak blocked
    leak = client.get(
        f"/api/v1/accommodations/{lid}?section_id={SECTION}",
        headers=auth_header(peer["token"]),
    )
    assert leak.status_code == 403
    # Learner cannot see private notes
    self_view = client.get(
        f"/api/v1/accommodations/{lid}?section_id={SECTION}",
        headers=auth_header(learner["token"]),
    )
    assert self_view.status_code == 200
    assert "notes_private" not in self_view.json() or self_view.json().get("notes_private") in (None, "")
    # Behavior: attempt override allows more attempts — consume 2 default would fail without override
    h = auth_header(learner["token"])
    for i in range(3):
        start = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=h)
        assert start.status_code == 200, start.text
        client.post(
            f"/api/v1/quiz-attempts/{start.json()['attempt_id']}/submit",
            headers=h,
            json={"responses": {}, "client_mutation_id": f"mut_acc_quiz_{i:02d}_xxxx"},
        )
    # Audit exists
    audits = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE action='accommodation_upsert'"
    ).fetchone()["c"]
    assert audits >= 1
