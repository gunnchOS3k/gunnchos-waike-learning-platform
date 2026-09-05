"""Transaction integrity: a refused mutation must leave no domain writes behind.

Rejections and conflicts run far enough into the code to touch domain tables before
they fail. Savepoints are what keep those partial writes from surviving, while still
letting the mutation ledger record that the attempt happened.
"""

from __future__ import annotations

from helpers import SECTION, auth_header, login

QUIZ = "quiz_dc_w01_gate_a"


def _counts(db) -> dict[str, int]:
    tables = (
        "lesson_progress",
        "draft_versions",
        "attachment_blobs",
        "quiz_attempts",
        "quiz_responses",
        "lab_runs",
        "discussion_posts",
    )
    out = {}
    for t in tables:
        out[t] = db.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
    return out


def _mutate(client, token: str, **body):
    payload = {
        "client_mutation_id": "mut_txn_default_001",
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "dev_txn",
        "entity_type": "lesson_progress",
        "entity_id": "L1",
        "base_revision": 0,
        "operation": "upsert",
        "payload": {"pack_id": "pack_dc", "lesson_id": "L1", "percent_complete": 10},
    }
    payload.update(body)
    return client.post("/api/v1/sync/mutations", headers=auth_header(token), json=payload)


def test_rejected_mutation_writes_no_domain_rows_but_is_still_recorded(client, prod_app):
    learner = login(client, "learner-alpha")
    db = prod_app.state.db
    before = _counts(db)
    ledger_before = db.execute("SELECT COUNT(*) AS c FROM sync_mutations").fetchone()["c"]

    r = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_reject_0001",
        entity_type="attachment",
        entity_id="mut_txn_reject_0001",
        payload={
            "content_base64": "not-valid-base64!!",
            "filename": "x.txt",
            "mime_type": "text/plain",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["sync_status"] in {"rejected", "quarantined"}
    assert r.json()["ack_durable"] is False

    after = _counts(db)
    assert after == before, f"rejected mutation left domain writes: {before} -> {after}"

    # The attempt itself is on the ledger, so the client can stop retrying it.
    ledger_after = db.execute("SELECT COUNT(*) AS c FROM sync_mutations").fetchone()["c"]
    assert ledger_after == ledger_before + 1
    receipt = client.get(
        "/api/v1/sync/receipts/mut_txn_reject_0001", headers=auth_header(learner["token"])
    )
    assert receipt.status_code == 200
    assert receipt.json()["result"] != "ok"


def test_conflicted_draft_leaves_the_stored_revision_untouched(client, prod_app):
    learner = login(client, "learner-alpha")
    db = prod_app.state.db
    assignment = client.get(
        "/api/v1/assignments", headers=auth_header(learner["token"])
    ).json()[0]["assignment_id"]

    first = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_conflict_a1",
        entity_type="assignment_draft",
        entity_id=assignment,
        payload={"text_response": "authoritative text"},
    )
    assert first.json()["sync_status"] == "acknowledged", first.text

    versions_before = db.execute(
        "SELECT COUNT(*) AS c FROM draft_versions WHERE entity_id=?", (assignment,)
    ).fetchone()["c"]

    stale = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_conflict_a2",
        entity_type="assignment_draft",
        entity_id=assignment,
        base_revision=0,
        payload={"text_response": "stale overwrite"},
    )
    assert stale.json()["sync_status"] == "conflict", stale.text

    versions_after = db.execute(
        "SELECT COUNT(*) AS c FROM draft_versions WHERE entity_id=?", (assignment,)
    ).fetchone()["c"]
    assert versions_after == versions_before, "a conflicting write still created a version"

    # The offline draft ledger keeps its own revisions, separate from the PR2 draft
    # endpoint, so the check belongs against the revision the sync path wrote.
    latest = db.execute(
        "SELECT payload_json FROM draft_versions WHERE entity_id=? "
        "ORDER BY revision DESC LIMIT 1",
        (assignment,),
    ).fetchone()
    assert "authoritative text" in latest["payload_json"]
    assert "stale overwrite" not in latest["payload_json"]

    pulled = client.get(
        f"/api/v1/sync/pull?section_id={SECTION}", headers=auth_header(learner["token"])
    ).json()
    drafts = [d for d in pulled["draft_versions"] if d["entity_id"] == assignment]
    assert drafts, "the surviving draft must be visible to the client"
    assert all("stale overwrite" not in str(d["payload"]) for d in drafts)


def test_unauthorized_mutation_writes_nothing_anywhere(client, prod_app):
    learner = login(client, "learner-alpha")
    db = prod_app.state.db
    before = _counts(db)
    ledger_before = db.execute("SELECT COUNT(*) AS c FROM sync_mutations").fetchone()["c"]

    r = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_unauth_0001",
        section_id="sec_beta_dc_w01",
    )
    assert r.status_code in (403, 404) or r.json()["sync_status"] == "rejected", r.text

    assert _counts(db) == before
    # An unauthorized caller must not even be able to grow the ledger unboundedly.
    ledger_after = db.execute("SELECT COUNT(*) AS c FROM sync_mutations").fetchone()["c"]
    assert ledger_after - ledger_before <= 1


def test_failed_quiz_sync_does_not_half_submit_an_attempt(client, prod_app):
    """A quiz_attempt mutation aimed at the wrong section must not mark it submitted."""
    learner = login(client, "learner-alpha")
    db = prod_app.state.db
    attempt = client.post(
        f"/api/v1/quizzes/{QUIZ}/attempts", headers=auth_header(learner["token"])
    ).json()
    responses_before = db.execute(
        "SELECT COUNT(*) AS c FROM quiz_responses WHERE attempt_id=?",
        (attempt["attempt_id"],),
    ).fetchone()["c"]

    r = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_quizmiss_01",
        entity_type="quiz_attempt",
        entity_id=attempt["attempt_id"],
        operation="submit",
        section_id="sec_beta_dc_w01",
        payload={"attempt_id": attempt["attempt_id"], "responses": {"qi_tf": True}},
    )
    assert r.status_code in (403, 404) or r.json()["sync_status"] != "acknowledged", r.text

    row = db.execute(
        "SELECT status FROM quiz_attempts WHERE attempt_id=?", (attempt["attempt_id"],)
    ).fetchone()
    assert row["status"] == "in_progress"
    responses_after = db.execute(
        "SELECT COUNT(*) AS c FROM quiz_responses WHERE attempt_id=?",
        (attempt["attempt_id"],),
    ).fetchone()["c"]
    assert responses_after == responses_before


def test_a_successful_mutation_commits_both_ledger_and_domain(client, prod_app):
    """The positive control: savepoints must not silently discard good writes."""
    learner = login(client, "learner-alpha")
    db = prod_app.state.db

    r = _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_success_001",
        payload={"pack_id": "pack_dc", "lesson_id": "L_txn", "percent_complete": 42},
    )
    assert r.json()["sync_status"] == "acknowledged", r.text
    assert r.json()["ack_durable"] is True

    progress = db.execute(
        "SELECT percent_complete FROM lesson_progress WHERE lesson_id=? AND user_id=?",
        ("L_txn", learner["user"]["user_id"]),
    ).fetchone()
    assert progress is not None and progress["percent_complete"] == 42

    ledger = db.execute(
        "SELECT sync_status FROM sync_mutations WHERE client_mutation_id=?",
        ("mut_txn_success_001",),
    ).fetchone()
    assert ledger["sync_status"] == "acknowledged"
    receipt = db.execute(
        "SELECT result FROM sync_receipts WHERE client_mutation_id=?",
        ("mut_txn_success_001",),
    ).fetchone()
    assert receipt["result"] == "ok"


def test_manual_grade_failure_leaves_no_partial_score(client, prod_app):
    learner = login(client, "learner-alpha")
    staff = login(client, "instructor-alpha")
    db = prod_app.state.db
    lh = auth_header(learner["token"])
    attempt = client.post(f"/api/v1/quizzes/{QUIZ}/attempts", headers=lh).json()
    client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/submit",
        headers=lh,
        json={"responses": {"qi_file": {"note": "work"}}},
    )
    before = db.execute(
        "SELECT points_earned, manual_graded, manual_comment FROM quiz_responses "
        "WHERE attempt_id=? AND item_id='qi_file'",
        (attempt["attempt_id"],),
    ).fetchone()

    # Out-of-range points: the comment must not land either.
    bad = client.post(
        f"/api/v1/quiz-attempts/{attempt['attempt_id']}/manual-grade",
        headers=auth_header(staff["token"]),
        json={"item_id": "qi_file", "points": 999, "comment": "should not persist"},
    )
    assert bad.status_code in (400, 422), bad.text

    after = db.execute(
        "SELECT points_earned, manual_graded, manual_comment FROM quiz_responses "
        "WHERE attempt_id=? AND item_id='qi_file'",
        (attempt["attempt_id"],),
    ).fetchone()
    assert after["points_earned"] == before["points_earned"]
    assert after["manual_graded"] == before["manual_graded"]
    assert after["manual_comment"] == before["manual_comment"]
    assert after["manual_comment"] != "should not persist"


def test_no_stale_savepoints_remain_after_a_mixed_batch(client, prod_app):
    """After a run of successes and failures the connection must be clean."""
    learner = login(client, "learner-alpha")
    db = prod_app.state.db

    _mutate(client, learner["token"], client_mutation_id="mut_txn_mixed_ok01")
    _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_mixed_bad1",
        entity_type="totally_unknown_entity",
        entity_id="x",
    )
    _mutate(
        client,
        learner["token"],
        client_mutation_id="mut_txn_mixed_ok02",
        payload={"pack_id": "pack_dc", "lesson_id": "L_mixed", "percent_complete": 5},
    )

    # A leaked savepoint would make this fail or hang.
    assert not db.in_transaction, "connection left inside an open transaction"
    db.execute("BEGIN IMMEDIATE")
    db.execute("ROLLBACK")

    final = client.get(
        f"/api/v1/sync/pull?section_id={SECTION}", headers=auth_header(learner["token"])
    )
    assert final.status_code == 200
    lessons = {p["lesson_id"] for p in final.json()["lesson_progress"]}
    assert "L_mixed" in lessons
