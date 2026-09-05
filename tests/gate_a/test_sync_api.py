"""Sync API surface."""

from helpers import SECTION, auth_header, login


def test_sync_pull_and_receipt(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    mid = "mut_api_progress_abc"
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": mid,
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "api-dev",
            "entity_type": "lesson_progress",
            "entity_id": "L1",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "pack", "lesson_id": "L1", "percent_complete": 55},
        },
    )
    assert r.status_code == 200
    receipt = client.get(f"/api/v1/sync/receipts/{mid}", headers=h)
    assert receipt.status_code == 200
    assert receipt.json()["result"] == "ok"
    pull = client.get(f"/api/v1/sync/pull?section_id={SECTION}", headers=h)
    assert pull.status_code == 200
    assert any(p["lesson_id"] == "L1" for p in pull.json()["lesson_progress"])


def test_cross_site_mutation_denied(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": "mut_cross_site_deny1",
            "site_id": "site-beta",
            "section_id": SECTION,
            "device_id": "api-dev",
            "entity_type": "lesson_progress",
            "entity_id": "L2",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "p", "lesson_id": "L2", "percent_complete": 1},
        },
    )
    assert r.status_code == 403
