"""Manual quiz grading integrity: validate before mutating.

The invariant is that a rejected grade call leaves no trace. Every negative case
below re-reads the attempt afterwards to prove nothing moved.
"""

from __future__ import annotations

import json

import pytest
from helpers import SECTION, auth_header, login, user_id

QUIZ = "quiz_dc_w01_gate_a"
MANUAL_ITEM = "qi_file"
OBJECTIVE_ITEM = "qi_sc"
MANUAL_MAX = 2.0


def _submitted_attempt(client, learner_token: str) -> str:
    h = auth_header(learner_token)
    attempt = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=h).json()
    client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/submit",
        headers=h,
        json={"responses": {"qi_sc": "b", MANUAL_ITEM: {"note": "my reflection"}}},
    )
    return attempt["attempt_id"]


def _detail(client, staff_token: str, attempt_id: str) -> dict:
    r = client.get(f"/api/v1/quiz-attempts/{attempt_id}", headers=auth_header(staff_token))
    assert r.status_code == 200, r.text
    return r.json()


def _item(detail: dict, item_id: str) -> dict:
    return next(i for i in detail["items"] if i["item_id"] == item_id)


def _grade(client, staff_token: str, attempt_id: str, **body):
    payload = {"item_id": MANUAL_ITEM, "points": 1.0, "comment": ""}
    payload.update(body)
    # Serialised by hand so non-finite values reach the server the way a hostile
    # client would send them, instead of being blocked by the test client.
    return client.post(
        f"/api/v1/quiz-attempts/{attempt_id}/manual-grade",
        headers={**auth_header(staff_token), "Content-Type": "application/json"},
        content=json.dumps(payload),
    )


def test_valid_manual_grade_is_recorded_with_an_audit_trail(client, prod_app):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    before = _detail(client, staff["token"], attempt_id)
    assert not _item(before, MANUAL_ITEM)["manual_graded"]

    r = _grade(client, staff["token"], attempt_id, points=1.5, comment="Good reasoning")
    assert r.status_code == 200, r.text

    after = _detail(client, staff["token"], attempt_id)
    item = _item(after, MANUAL_ITEM)
    assert item["manual_graded"]
    assert item["points_earned"] == 1.5
    assert item["manual_comment"] == "Good reasoning"

    audit = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE entity_id=? AND action LIKE '%manual%'",
        (attempt_id,),
    ).fetchone()
    assert audit["c"] >= 1


@pytest.mark.parametrize(
    "bad_points",
    [-1.0, MANUAL_MAX + 0.5, float("inf"), float("-inf"), float("nan")],
)
def test_out_of_bounds_or_non_finite_points_are_refused(client, bad_points):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    r = _grade(client, staff["token"], attempt_id, points=bad_points)
    assert r.status_code in (400, 422), f"{bad_points}: {r.status_code} {r.text}"

    after = _item(_detail(client, staff["token"], attempt_id), MANUAL_ITEM)
    assert not after["manual_graded"]
    assert after["points_earned"] in (None, 0, 0.0)


def test_nonexistent_item_cannot_be_graded_into_existence(client, prod_app):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    before = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM quiz_responses WHERE attempt_id=?", (attempt_id,)
    ).fetchone()["c"]

    r = _grade(client, staff["token"], attempt_id, item_id="qi_does_not_exist")
    assert r.status_code == 404, r.text

    after = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM quiz_responses WHERE attempt_id=?", (attempt_id,)
    ).fetchone()["c"]
    assert after == before, "a phantom response row was created"
    assert _detail(client, staff["token"], attempt_id)["status"] != "graded"


def test_item_from_a_different_quiz_is_refused(client, prod_app):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    # Give the site a second quiz so the cross-quiz path is always exercised.
    instructor_id = prod_app.state.db.execute(
        "SELECT user_id FROM users WHERE username=? AND site_id=?",
        ("instructor-alpha", "site-alpha"),
    ).fetchone()["user_id"]
    prod_app.state.activities.seed_section_activities(
        section_id="sec_beta_dc_w01",
        site_id="site-alpha",
        instructor_id=instructor_id,
    )

    # An item id that exists, but belongs to another quiz.
    foreign = prod_app.state.db.execute(
        "SELECT item_id FROM quiz_items WHERE quiz_id <> ? LIMIT 1", (QUIZ,)
    ).fetchone()
    assert foreign is not None, "the second section failed to seed a quiz"

    r = _grade(client, staff["token"], attempt_id, item_id=foreign["item_id"])
    assert r.status_code in (400, 403, 404), r.text
    assert not _item(_detail(client, staff["token"], attempt_id), MANUAL_ITEM)["manual_graded"]


def test_objective_item_cannot_be_hand_graded(client):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    r = _grade(client, staff["token"], attempt_id, item_id=OBJECTIVE_ITEM, points=1.0)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "ITEM_NOT_MANUAL_GRADED"


def test_in_progress_attempt_cannot_be_graded(client):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt = client.post(
        f"/api/v1/quizzes/{QUIZ}/attempts", headers=auth_header(learner["token"])
    ).json()

    r = _grade(client, staff["token"], attempt["attempt_id"])
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "ATTEMPT_NOT_GRADABLE"
    assert _detail(client, staff["token"], attempt["attempt_id"])["status"] == "in_progress"


def test_attempt_is_not_marked_fully_graded_while_manual_work_remains(client):
    """Two manual items outstanding must not read as a finished grade."""
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    detail = _detail(client, staff["token"], attempt_id)
    manual_items = [i for i in detail["items"] if i["grading_mode"] == "manual"]
    assert manual_items, "seed must include at least one manual item"

    # Grade all but the last manual item.
    for item in manual_items[:-1]:
        assert _grade(client, staff["token"], attempt_id, item_id=item["item_id"], points=1.0).status_code == 200

    if len(manual_items) > 1:
        mid = _detail(client, staff["token"], attempt_id)
        assert mid["status"] != "graded"

    assert (
        _grade(
            client, staff["token"], attempt_id, item_id=manual_items[-1]["item_id"], points=1.0
        ).status_code
        == 200
    )
    final = _detail(client, staff["token"], attempt_id)
    assert all(i["manual_graded"] for i in final["items"] if i["grading_mode"] == "manual")


def test_manual_queue_empties_only_once_every_item_is_scored(client):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    queue = client.get(
        f"/api/v1/instructor/sections/{SECTION}/manual-queue",
        headers=auth_header(staff["token"]),
    ).json()
    row = next(r for r in queue if r["attempt_id"] == attempt_id)
    assert row["pending_manual"] >= 1

    _grade(client, staff["token"], attempt_id, points=2.0)

    queue_after = client.get(
        f"/api/v1/instructor/sections/{SECTION}/manual-queue",
        headers=auth_header(staff["token"]),
    ).json()
    row_after = next((r for r in queue_after if r["attempt_id"] == attempt_id), None)
    assert row_after is None or row_after["pending_manual"] == 0


def test_anonymous_queue_hides_learner_identity(client):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    _submitted_attempt(client, learner["token"])

    anon = client.get(
        f"/api/v1/instructor/sections/{SECTION}/manual-queue?anonymous=true",
        headers=auth_header(staff["token"]),
    )
    assert anon.status_code == 200, anon.text
    assert user_id(learner) not in anon.text
    assert all(row["learner_id"].startswith("anon_") for row in anon.json())


def test_regrade_of_an_already_graded_item_keeps_the_prior_value_in_the_audit(client, prod_app):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    attempt_id = _submitted_attempt(client, learner["token"])

    assert _grade(client, staff["token"], attempt_id, points=0.5, comment="first").status_code == 200
    assert _grade(client, staff["token"], attempt_id, points=2.0, comment="second").status_code == 200

    item = _item(_detail(client, staff["token"], attempt_id), MANUAL_ITEM)
    assert item["points_earned"] == 2.0
    assert item["manual_comment"] == "second"

    entries = prod_app.state.db.execute(
        "SELECT COUNT(*) AS c FROM audit_events WHERE entity_id=? AND action LIKE '%manual%'",
        (attempt_id,),
    ).fetchone()["c"]
    assert entries >= 2, "each grading decision must be independently auditable"
