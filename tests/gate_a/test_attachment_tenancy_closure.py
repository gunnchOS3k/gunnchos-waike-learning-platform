"""Attachment tenancy and path-resolution closure.

Two failure modes are covered here: content-hash dedup that crosses a tenancy
boundary (site B learns a blob exists because site A uploaded the same bytes), and
storage paths resolved by string prefix rather than by real containment.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from helpers import SECTION, auth_header, login

BETA_SECTION = "sec_beta_dc_w01"
SHARED_BYTES = b"identical evidence bytes across tenants"


def _domain(response) -> dict:
    """Unwrap the /sync/mutations envelope to the domain result it carried."""
    return response.json().get("result") or {}


def _error(response) -> str | None:
    body = response.json()
    if response.status_code != 200:
        return body.get("detail")
    return _domain(response).get("error")


def _attach(client, token: str, mid: str, *, section_id=SECTION, site_id="site-alpha", **payload):
    body = {
        "content_base64": base64.b64encode(SHARED_BYTES).decode(),
        "filename": "evidence.txt",
        "mime_type": "text/plain",
    }
    body.update(payload)
    return client.post(
        "/api/v1/sync/mutations",
        headers=auth_header(token),
        json={
            "client_mutation_id": mid,
            "site_id": site_id,
            "section_id": section_id,
            "device_id": "dev_attach",
            "entity_type": "attachment",
            "entity_id": mid,
            "base_revision": 0,
            "operation": "upsert",
            "payload": body,
        },
    )


def test_identical_bytes_in_two_sites_are_two_distinct_blobs(client):
    alpha = login(client, "learner-alpha")
    gamma = login(client, "learner-gamma", "site-beta")

    a = _attach(client, alpha["token"], "mut_attach_site_a01")
    assert a.status_code == 200, a.text
    assert a.json()["sync_status"] == "acknowledged"
    assert not _domain(a).get("deduplicated")

    b = _attach(
        client,
        gamma["token"],
        "mut_attach_site_b01",
        section_id=BETA_SECTION,
        site_id="site-beta",
    )
    assert b.status_code == 200, b.text
    # Crucially: site B must not be handed site A's blob id, nor told it deduplicated.
    assert not _domain(b).get("deduplicated")
    assert _domain(b)["entity_id"] != _domain(a)["entity_id"]
    assert _domain(b)["site_id"] == "site-beta"


def test_dedup_within_a_site_never_returns_an_unauthorized_section(client, prod_app):
    """Same bytes, same site, but persisted under a section the caller cannot see."""
    alpha = login(client, "learner-alpha")
    first = _attach(client, alpha["token"], "mut_attach_dedup_a1")
    assert first.status_code == 200, first.text
    blob_id = _domain(first)["entity_id"]

    # Move the stored blob to a section this learner is not enrolled in.
    admin = login(client, "admin-alpha")
    pkg = prod_app.state.db.execute("SELECT package_id FROM packages LIMIT 1").fetchone()
    other = client.post(
        "/api/v1/admin/sections",
        headers=auth_header(admin["token"]),
        json={"code": "DC-ATT", "title": "Attachment Scope", "package_id": pkg["package_id"]},
    )
    assert other.status_code in (200, 201), other.text
    hidden_section = other.json()["section_id"]
    prod_app.state.db.execute(
        "UPDATE attachment_blobs SET section_id=? WHERE blob_id=?", (hidden_section, blob_id)
    )
    prod_app.state.db.commit()

    replay = _attach(client, alpha["token"], "mut_attach_dedup_a2")
    assert _error(replay) == "ATTACHMENT_SCOPE_DENIED", replay.text
    assert replay.json()["sync_status"] == "rejected"
    # The other section's blob id must not leak through the refusal.
    assert blob_id not in replay.text


def test_learner_cannot_attach_into_a_section_they_are_not_in(client):
    alpha = login(client, "learner-alpha")
    r = _attach(client, alpha["token"], "mut_attach_wrong_sec1", section_id=BETA_SECTION)
    if r.status_code == 200:
        assert r.json()["sync_status"] == "rejected", r.text
    else:
        assert r.status_code in (403, 404), r.text


@pytest.mark.parametrize(
    "filename",
    [
        "../../../../etc/passwd",
        "..\\..\\windows\\system32\\config",
        "/etc/shadow",
        "~/.ssh/id_rsa",
        "nested/dir/file.txt",
        "..",
    ],
)
def test_path_traversal_filenames_are_refused(client, filename):
    alpha = login(client, "learner-alpha")
    r = _attach(
        client,
        alpha["token"],
        f"mut_attach_trav_{abs(hash(filename)) % 10**6:06d}",
        filename=filename,
    )
    assert _error(r) == "PATH_TRAVERSAL", r.text


def test_every_stored_blob_stays_inside_the_blob_root(client, prod_app):
    alpha = login(client, "learner-alpha")
    ok = _attach(client, alpha["token"], "mut_attach_root_ok01")
    assert ok.json()["sync_status"] == "acknowledged", ok.text

    root = Path(prod_app.state.sync.blob_root).resolve()
    rows = prod_app.state.db.execute("SELECT storage_path FROM attachment_blobs").fetchall()
    assert rows, "expected at least one stored blob"
    for row in rows:
        stored = Path(row["storage_path"]).resolve()
        # Containment, not a string prefix: a sibling like `<root>-evil` must not pass.
        assert stored.is_relative_to(root), stored


def test_claimed_hash_must_match_the_bytes(client):
    alpha = login(client, "learner-alpha")
    r = _attach(
        client,
        alpha["token"],
        "mut_attach_hash_bad1",
        content_hash="0" * 64,
    )
    assert _error(r) == "HASH_MISMATCH", r.text
    assert r.json()["sync_status"] == "rejected"


def test_disallowed_mime_is_refused(client):
    alpha = login(client, "learner-alpha")
    r = _attach(
        client,
        alpha["token"],
        "mut_attach_mime_bad1",
        mime_type="application/x-msdownload",
    )
    assert _error(r) == "MIME_DENIED", r.text
    # Quarantined rather than dropped: the attempt stays visible to staff.
    assert r.json()["sync_status"] == "quarantined"
    assert r.json()["ack_durable"] is False


def test_quarantined_attachment_is_retained_as_evidence(client, prod_app):
    """A rejected upload must still leave a record; silently dropping it loses evidence."""
    alpha = login(client, "learner-alpha")
    r = _attach(
        client,
        alpha["token"],
        "mut_attach_quarant_1",
        force_quarantine=True,
        content_base64=base64.b64encode(b"suspicious payload").decode(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["sync_status"] == "quarantined"
    domain = _domain(r)
    assert domain["quarantined"] is True

    row = prod_app.state.db.execute(
        "SELECT quarantined FROM attachment_blobs WHERE blob_id=?", (domain["entity_id"],)
    ).fetchone()
    assert row is not None and row["quarantined"] == 1
    # The mutation itself is still on the ledger.
    receipt = client.get(
        "/api/v1/sync/receipts/mut_attach_quarant_1", headers=auth_header(alpha["token"])
    )
    assert receipt.status_code == 200
