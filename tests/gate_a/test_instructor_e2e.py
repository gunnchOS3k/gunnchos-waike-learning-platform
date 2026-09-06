"""Instructor E2E for Gate A activity + grading efficiency."""

from helpers import SECTION, auth_header, login, user_id


def test_instructor_console_flow(client):
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
                "qi_sc": "a",
                "qi_ms": ["a"],
                "qi_tf": False,
                "qi_num": 1,
                "qi_short": "nope",
                "qi_file": {"f": 1},
            },
            "client_mutation_id": "mut_inst_e2e_01",
        },
    )
    dash = client.get(
        f"/api/v1/instructor/sections/{SECTION}/dashboard",
        headers=ih,
    )
    assert dash.status_code == 200
    nxt = client.get(
        f"/api/v1/instructor/sections/{SECTION}/next-ungraded",
        headers=ih,
    )
    assert nxt.json()["next"] is not None
    client.post(
        f"/api/v1/quiz-attempts/{aid}/manual-grade",
        headers=ih,
        json={"item_id": "qi_file", "points": 1},
    )
    prog = client.get(
        f"/api/v1/instructor/sections/{SECTION}/grading-progress",
        headers=ih,
    )
    assert prog.json()["graded"] >= 1
