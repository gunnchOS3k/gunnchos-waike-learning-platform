"""Attachment / blob security."""

import base64

from helpers import SECTION, auth_header, login


def test_path_traversal_rejected(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    for name in ["../etc/passwd", "..\\secret", "/abs/path.txt", "a/b.txt"]:
        r = client.post(
            "/api/v1/sync/mutations",
            headers=h,
            json={
                "client_mutation_id": f"mut_path_{abs(hash(name))%10**8:08d}",
                "site_id": "site-alpha",
                "section_id": SECTION,
                "device_id": "att",
                "entity_type": "attachment",
                "entity_id": "x",
                "base_revision": 0,
                "operation": "upload",
                "payload": {
                    "filename": name,
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode(b"x").decode(),
                },
            },
        )
        assert r.status_code == 200
        assert r.json()["sync_status"] == "quarantined"


def test_mime_and_size(client):
    sess = login(client, "learner-alpha")
    h = auth_header(sess["token"])
    r = client.post(
        "/api/v1/sync/mutations",
        headers=h,
        json={
            "client_mutation_id": "mut_mime_bad_0001",
            "site_id": "site-alpha",
            "section_id": SECTION,
            "device_id": "att",
            "entity_type": "attachment",
            "entity_id": "x",
            "base_revision": 0,
            "operation": "upload",
            "payload": {
                "filename": "x.exe",
                "mime_type": "application/x-msdownload",
                "content_base64": base64.b64encode(b"MZ").decode(),
            },
        },
    )
    assert r.json()["sync_status"] == "quarantined"
