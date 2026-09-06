"""Quiz engine + security."""

from helpers import SECTION, auth_header, login, user_id


def test_quiz_objective_grading_and_answer_key_isolation(client):
    learner = login(client, "learner-alpha")
    peer = login(client, "learner-beta")
    inst = login(client, "instructor-alpha")
    lh = auth_header(learner["token"])
    view = client.get("/api/v1/quizzes/quiz_dc_w01_gate_a", headers=lh)
    assert view.status_code == 200
    assert "answer_key" not in view.json()
    assert all("correct" not in i for i in view.json()["items"])

    # Learner answer-key endpoint denied
    denied = client.get("/api/v1/quizzes/quiz_dc_w01_gate_a/answer-key", headers=lh)
    assert denied.status_code == 403

    key = client.get(
        "/api/v1/quizzes/quiz_dc_w01_gate_a/answer-key",
        headers=auth_header(inst["token"]),
    )
    assert key.status_code == 200
    assert "qi_sc" in key.json()["answer_key"]

    start = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    aid = start.json()["attempt_id"]
    sub = client.post(
        f"/api/v1/quiz-attempts/{aid}/submit",
        headers=lh,
        json={
            "responses": {
                "qi_sc": "b",
                "qi_ms": ["a", "c"],
                "qi_tf": True,
                "qi_num": 42,
                "qi_short": "digital confidence",
                "qi_file": {"blob": "x"},
            },
            "client_mutation_id": "mut_quiz_obj_01",
        },
    )
    assert sub.status_code == 200
    body = sub.json()
    assert body["answer_key_exposed"] is False
    assert body["status"] == "submitted"  # manual file item
    assert body["score"] == 6.0  # 1+2+1+1+1
    assert "qi_file" in body["manual_items"]

    # Attempt limit server-side
    start2 = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    assert start2.status_code == 200
    aid2 = start2.json()["attempt_id"]
    client.post(
        f"/api/v1/quiz-attempts/{aid2}/submit",
        headers=lh,
        json={"responses": {}, "client_mutation_id": "mut_quiz_obj_02"},
    )
    start3 = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    assert start3.status_code == 403
    assert start3.json()["detail"] == "ATTEMPT_LIMIT"

    # Role spoof / peer cannot grade
    spoof = client.post(
        f"/api/v1/quiz-attempts/{aid}/manual-grade",
        headers=auth_header(peer["token"]),
        json={"item_id": "qi_file", "points": 2},
    )
    assert spoof.status_code == 403
