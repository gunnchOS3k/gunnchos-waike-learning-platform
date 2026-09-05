"""Conflict policy tests."""

from helpers import SECTION, auth_header, login


def test_draft_conflict_preserves_versions(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    body = {
        "client_mutation_id": "mut_draft_v1_aaaa",
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "cdev",
        "entity_type": "assignment_draft",
        "entity_id": "draft_assign_1",
        "base_revision": 0,
        "operation": "save",
        "payload": {"draft_key": "draft_assign_1", "text_response": "v1"},
    }
    assert client.post("/api/v1/sync/mutations", headers=h, json=body).status_code == 200
    body2 = dict(body)
    body2["client_mutation_id"] = "mut_draft_conflict_bb"
    body2["base_revision"] = 0  # stale
    body2["payload"] = {"draft_key": "draft_assign_1", "text_response": "v2-stale"}
    r = client.post("/api/v1/sync/mutations", headers=h, json=body2)
    assert r.status_code == 200
    assert r.json()["sync_status"] == "conflict"
    versions = client.app.state.db.execute(
        "SELECT COUNT(*) AS c FROM draft_versions WHERE draft_key=?",
        ("draft_assign_1",),
    ).fetchone()["c"]
    assert versions == 1  # stale write rejected; prior preserved


def test_progress_conflict(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    b1 = {
        "client_mutation_id": "mut_prog_ok_0001",
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "cdev",
        "entity_type": "lesson_progress",
        "entity_id": "conflict-lesson",
        "base_revision": 0,
        "operation": "upsert",
        "payload": {"pack_id": "p", "lesson_id": "conflict-lesson", "percent_complete": 20},
    }
    assert client.post("/api/v1/sync/mutations", headers=h, json=b1).status_code == 200
    b2 = dict(b1)
    b2["client_mutation_id"] = "mut_prog_conflict01"
    b2["base_revision"] = 0
    b2["payload"] = {"pack_id": "p", "lesson_id": "conflict-lesson", "percent_complete": 99}
    r = client.post("/api/v1/sync/mutations", headers=h, json=b2)
    assert r.json()["sync_status"] == "conflict"
