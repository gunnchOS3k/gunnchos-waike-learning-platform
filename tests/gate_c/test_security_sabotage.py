"""Gate C authorization / archive / session sabotage highlights."""

from __future__ import annotations

from helpers import auth_header, login


def test_cross_site_deep_link(client):
    h = auth_header(login(client, "learner-gamma", "site-beta")["token"])
    # Alpha section id from another site
    r = client.post(
        "/api/v1/deviceos/deep-link",
        headers=h,
        json={"uri": "waike://section/sec_alpha_dc_w01"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "DEEP_LINK_CROSS_SITE"


def test_learner_cannot_admin_backup(client):
    h = auth_header(login(client, "learner-alpha")["token"])
    r = client.post("/api/v1/admin/backup", headers=h)
    assert r.status_code == 403


def test_grader_cannot_site_admin_oneroster(client):
    h = auth_header(login(client, "grader-alpha")["token"])
    r = client.post(
        "/api/v1/interop/oneroster/import",
        headers=h,
        json={"entity_file": "orgs", "csv_text": "sourcedId,name,status\nx,y,active\n"},
    )
    assert r.status_code == 403
