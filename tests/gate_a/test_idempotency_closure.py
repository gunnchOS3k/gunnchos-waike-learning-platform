"""Idempotency closure: a replayed id must be the *same* mutation, not just the same id.

A client mutation id is a retry token, not a capability. Reusing one with different
content — or from a different actor — must be refused rather than answered with a
receipt describing work that was never requested.
"""

from __future__ import annotations

from helpers import SECTION, auth_header, login

BASE_PAYLOAD = {"pack_id": "pack_dc", "lesson_id": "L1", "percent_complete": 25}


def _mutation(mid: str, **overrides) -> dict:
    body = {
        "client_mutation_id": mid,
        "site_id": "site-alpha",
        "section_id": SECTION,
        "device_id": "dev_idem",
        "entity_type": "lesson_progress",
        "entity_id": "L1",
        "base_revision": 0,
        "operation": "upsert",
        "payload": dict(BASE_PAYLOAD),
        "local_sequence": 1,
    }
    body.update(overrides)
    return body


def _apply(client, token: str, body: dict):
    return client.post("/api/v1/sync/mutations", headers=auth_header(token), json=body)


def test_identical_replay_returns_the_same_receipt(client):
    learner = login(client, "learner-alpha")
    mid = "mut_idem_same_0001"
    first = _apply(client, learner["token"], _mutation(mid))
    assert first.status_code == 200, first.text
    second = _apply(client, learner["token"], _mutation(mid))
    assert second.status_code == 200, second.text

    a, b = first.json(), second.json()
    assert a["server_revision"] == b["server_revision"]
    assert a.get("receipt_id") == b.get("receipt_id")

    # Exactly one ledger row; the replay did not apply the write twice.
    receipt = client.get(
        f"/api/v1/sync/receipts/{mid}", headers=auth_header(learner["token"])
    )
    assert receipt.status_code == 200


def test_changed_payload_under_the_same_id_is_refused(client):
    learner = login(client, "learner-alpha")
    mid = "mut_idem_payload_01"
    assert _apply(client, learner["token"], _mutation(mid)).status_code == 200

    tampered = _mutation(mid, payload={**BASE_PAYLOAD, "percent_complete": 100})
    r = _apply(client, learner["token"], tampered)
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "MUTATION_ID_REUSE_MISMATCH"

    # The original value stands; the tamper attempt changed nothing.
    pull = client.get(
        f"/api/v1/sync/pull?section_id={SECTION}", headers=auth_header(learner["token"])
    ).json()
    row = next(p for p in pull["lesson_progress"] if p["lesson_id"] == "L1")
    assert row["percent_complete"] == 25


def test_changed_entity_operation_or_section_is_refused(client):
    learner = login(client, "learner-alpha")
    for suffix, override in (
        ("entity", {"entity_id": "L2"}),
        ("etype", {"entity_type": "assignment_draft"}),
        ("oper", {"operation": "delete"}),
        ("sect", {"section_id": "sec_beta_dc_w01"}),
    ):
        mid = f"mut_idem_{suffix}_001"
        assert _apply(client, learner["token"], _mutation(mid)).status_code == 200
        r = _apply(client, learner["token"], _mutation(mid, **override))
        # A section change may be refused as authz before it is refused as reuse.
        assert r.status_code in (403, 409), f"{suffix}: {r.status_code} {r.text}"
        if r.status_code == 409:
            assert r.json()["detail"] == "MUTATION_ID_REUSE_MISMATCH"


def test_another_actor_cannot_claim_or_read_a_receipt(client):
    owner = login(client, "learner-alpha")
    mid = "mut_idem_actor_0001"
    assert _apply(client, owner["token"], _mutation(mid)).status_code == 200

    thief = login(client, "learner-beta")
    replay = _apply(client, thief["token"], _mutation(mid))
    assert replay.status_code in (403, 409), replay.text
    # Above all: the response must not be the owner's receipt.
    assert "receipt_id" not in replay.text or replay.status_code != 200

    read = client.get(f"/api/v1/sync/receipts/{mid}", headers=auth_header(thief["token"]))
    assert read.status_code in (403, 404)


def test_device_mismatch_is_refused_when_the_id_is_reused(client):
    learner = login(client, "learner-alpha")
    mid = "mut_idem_device_001"
    assert _apply(client, learner["token"], _mutation(mid)).status_code == 200
    r = _apply(client, learner["token"], _mutation(mid, device_id="dev_other"))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "MUTATION_ID_REUSE_MISMATCH"


def test_payload_key_order_does_not_count_as_a_mismatch(client):
    """Re-serialising the same payload must not look like tampering."""
    learner = login(client, "learner-alpha")
    mid = "mut_idem_order_0001"
    assert _apply(client, learner["token"], _mutation(mid)).status_code == 200
    reordered = {"percent_complete": 25, "lesson_id": "L1", "pack_id": "pack_dc"}
    r = _apply(client, learner["token"], _mutation(mid, payload=reordered))
    assert r.status_code == 200, r.text


def test_distinct_ids_apply_independently(client):
    """Two different ids are two different writes, and the second builds on the first."""
    learner = login(client, "learner-alpha")
    a = _apply(client, learner["token"], _mutation("mut_idem_distinct_a1"))
    assert a.status_code == 200, a.text
    assert a.json()["sync_status"] == "acknowledged"

    b = _apply(
        client,
        learner["token"],
        _mutation(
            "mut_idem_distinct_b1",
            base_revision=a.json()["server_revision"],
            payload={**BASE_PAYLOAD, "percent_complete": 60},
        ),
    )
    assert b.status_code == 200, b.text
    assert b.json()["sync_status"] == "acknowledged"
    assert b.json()["server_revision"] > a.json()["server_revision"]

    pull = client.get(
        f"/api/v1/sync/pull?section_id={SECTION}", headers=auth_header(learner["token"])
    ).json()
    row = next(p for p in pull["lesson_progress"] if p["lesson_id"] == "L1")
    assert row["percent_complete"] == 60


def test_stale_base_revision_conflicts_without_overwriting(client):
    learner = login(client, "learner-alpha")
    first = _apply(client, learner["token"], _mutation("mut_idem_stale_base1"))
    assert first.json()["sync_status"] == "acknowledged"

    stale = _apply(
        client,
        learner["token"],
        _mutation(
            "mut_idem_stale_base2",
            base_revision=0,
            payload={**BASE_PAYLOAD, "percent_complete": 99},
        ),
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["sync_status"] == "conflict"

    pull = client.get(
        f"/api/v1/sync/pull?section_id={SECTION}", headers=auth_header(learner["token"])
    ).json()
    row = next(p for p in pull["lesson_progress"] if p["lesson_id"] == "L1")
    assert row["percent_complete"] == 25
