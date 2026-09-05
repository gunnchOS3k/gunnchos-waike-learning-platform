"""Sync mutation model + status vocabulary."""

from helpers import SECTION, auth_header, login, user_id


def test_mutation_fields_and_statuses(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    lease = client.post(
        "/api/v1/sync/leases",
        headers=h,
        json={"section_id": SECTION, "device_id": "dev-model"},
    ).json()
    mid = "mut_model_progress_001"
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": mid,
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "dev-model",
            "entity_type": "lesson_progress",
            "entity_id": "lesson-1",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {
                "pack_id": "pack_dc",
                "lesson_id": "lesson-1",
                "percent_complete": 40,
            },
            "lease_id": lease["lease_id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_status"] == "acknowledged"
    assert body["ack_durable"] is True
    assert body["receipt"]["client_mutation_id"] == mid
    assert body["receipt"]["payload_hash"]
    assert body["receipt"]["authoritative_revision"] >= 1


def test_lease_expiry_and_revocation(client, prod_app):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    lease = client.post(
        "/api/v1/sync/leases",
        headers=h,
        json={"section_id": SECTION, "device_id": "dev-lease", "ttl_hours": 72},
    ).json()
    # Force expiry in DB
    prod_app.state.db.execute(
        "UPDATE offline_leases SET expires_at='2000-01-01T00:00:00Z' WHERE lease_id=?",
        (lease["lease_id"],),
    )
    prod_app.state.db.commit()
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": "mut_expired_lease_01",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "dev-lease",
            "entity_type": "lesson_progress",
            "entity_id": "lesson-x",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "p", "lesson_id": "lesson-x", "percent_complete": 1},
            "lease_id": lease["lease_id"],
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "LEASE_EXPIRED"

    lease2 = client.post(
        "/api/v1/sync/leases",
        headers=h,
        json={"section_id": SECTION, "device_id": "dev-lease2"},
    ).json()
    inst = login(client, "instructor-alpha")
    rev = client.post(
        f"/api/v1/sync/leases/{lease2['lease_id']}/revoke",
        headers=auth_header(inst["token"]),
        json={"reason": "test"},
    )
    assert rev.status_code == 200
    r2 = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": "mut_revoked_lease_01",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "dev-lease2",
            "entity_type": "lesson_progress",
            "entity_id": "lesson-y",
            "base_revision": 0,
            "operation": "upsert",
            "payload": {"pack_id": "p", "lesson_id": "lesson-y", "percent_complete": 1},
            "lease_id": lease2["lease_id"],
        },
    )
    assert r2.status_code == 403
    assert r2.json()["detail"] == "LEASE_REVOKED"
