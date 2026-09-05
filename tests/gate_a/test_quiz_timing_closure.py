"""Server-authoritative quiz timing.

The deadline is derived from the server's own start time plus the accommodated
duration. A client may report elapsed time, but that report is advisory: it can
neither extend a deadline nor rescue a late submission.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from helpers import SECTION, auth_header, login, user_id

QUIZ = "quiz_dc_w01_gate_a"
ANSWERS = {"qi_sc": "b", "qi_ms": ["a", "c"], "qi_tf": True, "qi_num": 42}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _start(client, token: str) -> dict:
    r = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()


def _submit(client, token: str, attempt_id: str, **extra) -> dict:
    body = {"responses": dict(ANSWERS)}
    body.update(extra)
    r = client.post(
        f"/api/v1/quiz-attempts/{attempt_id}/submit", headers=auth_header(token), json=body
    )
    assert r.status_code == 200, r.text
    return r.json()


def _age_attempt(prod_app, attempt_id: str, minutes: int) -> None:
    """Rewind the server's own start/deadline to simulate elapsed wall-clock time."""
    row = prod_app.state.db.execute(
        "SELECT started_at, deadline_at FROM quiz_attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    shift = timedelta(minutes=minutes)
    started = (_parse(row["started_at"]) - shift).strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline = (
        (_parse(row["deadline_at"]) - shift).strftime("%Y-%m-%dT%H:%M:%SZ")
        if row["deadline_at"]
        else None
    )
    prod_app.state.db.execute(
        "UPDATE quiz_attempts SET started_at=?, deadline_at=? WHERE attempt_id=?",
        (started, deadline, attempt_id),
    )
    prod_app.state.db.commit()


def test_server_sets_the_deadline_from_its_own_clock(client):
    learner = login(client, "learner-alpha")
    attempt = _start(client, learner["token"])
    assert attempt["deadline_at"], attempt
    started, deadline = _parse(attempt["started_at"]), _parse(attempt["deadline_at"])
    # Seeded policy is a 30-minute limit with no accommodation.
    assert abs((deadline - started) - timedelta(minutes=30)) < timedelta(seconds=90)
    assert attempt["time_limit_minutes"] == 30


def test_submission_before_the_deadline_is_graded_normally(client):
    learner = login(client, "learner-alpha")
    attempt = _start(client, learner["token"])
    result = _submit(client, learner["token"], attempt["attempt_id"])
    assert result["status"] in {"graded", "submitted", "awaiting_manual"}
    assert not result.get("timed_out")
    assert result["score"] is not None


def test_submission_after_the_deadline_is_kept_but_not_auto_graded(client, prod_app):
    learner = login(client, "learner-alpha")
    attempt = _start(client, learner["token"])
    _age_attempt(prod_app, attempt["attempt_id"], minutes=120)

    result = _submit(client, learner["token"], attempt["attempt_id"])
    assert result["status"] == "timed_out", result
    # The work is preserved as evidence rather than discarded.
    detail = client.get(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}", headers=auth_header(learner["token"])
    ).json()
    assert detail["status"] == "timed_out"
    assert len(detail["responses"]) > 0
    # But it is not scored as if it were on-time work.
    assert detail["score"] in (None, 0, 0.0)

    row = prod_app.state.db.execute(
        "SELECT server_timed_out FROM quiz_attempts WHERE attempt_id=?",
        (attempt["attempt_id"],),
    ).fetchone()
    assert row["server_timed_out"] == 1


def test_a_lying_client_elapsed_time_changes_nothing(client, prod_app):
    """The client may claim it finished in 30 seconds; the server disagrees."""
    learner = login(client, "learner-alpha")
    late = _start(client, learner["token"])
    _age_attempt(prod_app, late["attempt_id"], minutes=120)
    lied = _submit(client, learner["token"], late["attempt_id"], client_elapsed_minutes=0.5)
    assert lied["status"] == "timed_out", lied

    # And the inverse lie cannot fail an on-time attempt either.
    on_time = _start(client, learner["token"])
    honest = _submit(
        client, learner["token"], on_time["attempt_id"], client_elapsed_minutes=9999
    )
    assert honest["status"] != "timed_out", honest


def test_accommodation_extends_the_server_deadline(client):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    saved = client.post(
        "/api/v1/accommodations",
        headers=auth_header(instructor["token"]),
        json={
            "learner_id": user_id(learner),
            "section_id": SECTION,
            "time_multiplier": 2.0,
        },
    )
    assert saved.status_code == 200, saved.text

    attempt = _start(client, learner["token"])
    span = _parse(attempt["deadline_at"]) - _parse(attempt["started_at"])
    assert abs(span - timedelta(minutes=60)) < timedelta(seconds=90), attempt
    assert attempt["time_limit_minutes"] == 60


def test_accommodated_learner_is_still_cut_off_past_the_longer_deadline(client, prod_app):
    instructor = login(client, "instructor-alpha")
    learner = login(client, "learner-alpha")
    client.post(
        "/api/v1/accommodations",
        headers=auth_header(instructor["token"]),
        json={"learner_id": user_id(learner), "section_id": SECTION, "time_multiplier": 2.0},
    )
    attempt = _start(client, learner["token"])
    # 90 minutes is inside neither the 30-minute base nor the 60-minute accommodation.
    _age_attempt(prod_app, attempt["attempt_id"], minutes=90)
    result = _submit(client, learner["token"], attempt["attempt_id"])
    assert result["status"] == "timed_out", result


def test_a_delayed_offline_sync_of_late_work_is_still_late(client, prod_app):
    """Queueing offline must not launder a missed deadline into on-time work."""
    learner = login(client, "learner-alpha")
    attempt = _start(client, learner["token"])
    _age_attempt(prod_app, attempt["attempt_id"], minutes=240)

    applied = client.post(
        "/api/v1/sync/mutations",
        headers=auth_header(learner["token"]),
        json={
            "client_mutation_id": "mut_quiz_late_sync_01",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "dev_quiz_offline",
            "entity_type": "quiz_attempt",
            "entity_id": attempt["attempt_id"],
            "base_revision": 0,
            "operation": "submit",
            "payload": {
                "attempt_id": attempt["attempt_id"],
                "responses": dict(ANSWERS),
                # The device swears it only took a minute.
                "client_elapsed_minutes": 1.0,
            },
        },
    )
    assert applied.status_code == 200, applied.text
    row = prod_app.state.db.execute(
        "SELECT status, server_timed_out FROM quiz_attempts WHERE attempt_id=?",
        (attempt["attempt_id"],),
    ).fetchone()
    assert row["status"] == "timed_out"
    assert row["server_timed_out"] == 1


def test_high_integrity_timed_quiz_is_not_offline_eligible(client, prod_app):
    """Trust boundary: a signed deadline is required before timing can go offline."""
    rows = prod_app.state.db.execute(
        "SELECT quiz_id, high_integrity_timed, offline_eligible FROM quiz_definitions"
    ).fetchall()
    for row in rows:
        if row["high_integrity_timed"]:
            assert not row["offline_eligible"], (
                f"{row['quiz_id']} is high-integrity timed and offline eligible; "
                "the client would own the clock"
            )
