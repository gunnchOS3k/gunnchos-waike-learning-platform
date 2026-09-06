"""Gradescope-style efficiency."""

from helpers import SECTION, auth_header, login


def test_next_ungraded_batch_regrade(client):
    learner = login(client, "learner-alpha")
    inst = login(client, "instructor-alpha")
    lh, ih = auth_header(learner["token"]), auth_header(inst["token"])
    start = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=lh)
    aid = start.json()["attempt_id"]
    client.post(
        f"/api/v1/quiz-attempts/{aid}/submit",
        headers=lh,
        json={
            "responses": {
                "qi_sc": "b",
                "qi_ms": ["a", "c"],
                "qi_tf": True,
                "qi_num": 42,
                "qi_short": "digital confidence",
                "qi_file": {"n": 1},
            },
            "client_mutation_id": "mut_grade_eff_01",
        },
    )
    nxt = client.get(
        f"/api/v1/instructor/sections/{SECTION}/next-ungraded?anonymous=true",
        headers=ih,
    )
    assert nxt.status_code == 200
    assert nxt.json()["ungraded_count"] >= 1
    assert nxt.json()["next"]["learner_id"].startswith("anon_")

    rc = client.post(
        "/api/v1/instructor/reusable-comments",
        headers=ih,
        json={"body": "Clear explanation", "section_id": SECTION, "criterion_id": "qi_file"},
    )
    assert rc.status_code == 200
    batch = client.post(
        "/api/v1/instructor/batch-criterion",
        headers=ih,
        json={
            "section_id": SECTION,
            "criterion_id": "qi_file",
            "points": 2,
            "attempt_ids": [aid],
            "comment": rc.json()["body"],
        },
    )
    assert batch.status_code == 200
    assert batch.json()["applied_count"] == 1
    prog = client.get(
        f"/api/v1/instructor/sections/{SECTION}/grading-progress",
        headers=ih,
    )
    assert prog.json()["graded"] >= 1
    rq = client.post(
        "/api/v1/instructor/regrade-queue",
        headers=auth_header(learner["token"]),
        json={"submission_id": aid, "reason": "please review"},
    )
    assert rq.status_code == 200
