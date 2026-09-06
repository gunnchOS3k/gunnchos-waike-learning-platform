"""Idempotency sabotage suite."""

import base64

from helpers import SECTION, auth_header, login


def test_duplicate_mutation_retry(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    body = {
        "client_mutation_id": "mut_idem_dup_0001",
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "idem-dev",
        "entity_type": "lesson_progress",
        "entity_id": "idem-lesson",
        "base_revision": 0,
        "operation": "upsert",
        "payload": {"pack_id": "p", "lesson_id": "idem-lesson", "percent_complete": 10},
    }
    r1 = client.post("/api/v1/sync/mutations", headers=h, json=body)
    r2 = client.post("/api/v1/sync/mutations", headers=h, json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["idempotent_replay"] is True
    rows = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM lesson_progress WHERE lesson_id=?",
        ("idem-lesson",),
    ).fetchone()["c"]
    assert rows == 1


def test_attachment_retry_dedup(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    content = base64.b64encode(b"hello-gate-a").decode()
    body = {
        "client_mutation_id": "mut_attach_retry_01",
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "idem-dev",
        "entity_type": "attachment",
        "entity_id": "file1",
        "base_revision": 0,
        "operation": "upload",
        "payload": {
            "filename": "note.txt",
            "mime_type": "text/plain",
            "content_base64": content,
        },
    }
    r1 = client.post("/api/v1/sync/mutations", headers=h, json=body)
    assert r1.status_code == 200
    body2 = dict(body)
    body2["client_mutation_id"] = "mut_attach_retry_02"
    r2 = client.post("/api/v1/sync/mutations", headers=h, json=body2)
    assert r2.status_code == 200
    assert r2.json()["result"]["deduplicated"] is True
    count = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM attachment_blobs"
    ).fetchone()["c"]
    assert count == 1


def test_quiz_submit_idempotent(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    start = client.post("/api/v1/quizzes/quiz_dc_w01_gate_a/attempts", headers=h)
    assert start.status_code == 200, start.text
    aid = start.json()["attempt_id"]
    payload = {
        "responses": {
            "qi_sc": "b",
            "qi_ms": ["a", "c"],
            "qi_tf": True,
            "qi_num": 42,
            "qi_short": "Digital Confidence",
            "qi_file": {"name": "x.txt"},
        },
        "client_mutation_id": "mut_quiz_idem_01",
    }
    r1 = client.post(f"/api/v1/quiz-attempts/{aid}/submit", headers=h, json=payload)
    r2 = client.post(f"/api/v1/quiz-attempts/{aid}/submit", headers=h, json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("idempotent_replay") is True
    attempts = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM quiz_attempts WHERE learner_id=? AND quiz_id=?",
        (sess["user"]["user_id"], "quiz_dc_w01_gate_a"),
    ).fetchone()["c"]
    assert attempts == 1
