"""Device OS bridge + profiles + deep links + continuity."""

from __future__ import annotations

from helpers import auth_header, login


def test_manifest_and_contracts(client):
    h = auth_header(login(client, "learner-alpha")["token"])
    m = client.get("/api/v1/deviceos/manifest", headers=h)
    assert m.status_code == 200
    assert m.json()["app_id"] == "com.gunnchos.waike.learning"
    c = client.get("/api/v1/deviceos/contracts", headers=h)
    assert c.status_code == 200
    assert "launcher" in c.json()["paths"]


def test_launcher_permissions(client):
    h = auth_header(login(client, "learner-alpha")["token"])
    la = client.get("/api/v1/deviceos/launcher", headers=h)
    assert la.json()["authority"] == "device_os"
    p = client.get("/api/v1/deviceos/permissions", headers=h)
    assert "files_read" in p.json()["allowed"]
    assert "ai_cloud_export" in p.json()["denied"]


def test_deep_link_requires_auth_and_rejects_bypass(client):
    # unauthenticated
    r = client.post("/api/v1/deviceos/deep-link", json={"uri": "waike://learn/home"})
    assert r.status_code in {401, 403}
    h = auth_header(login(client, "learner-alpha")["token"])
    ok = client.post("/api/v1/deviceos/deep-link", headers=h, json={"uri": "waike://learn/home"})
    assert ok.status_code == 200
    assert ok.json()["auth_bypassed"] is False
    bad = client.post("/api/v1/deviceos/deep-link", headers=h, json={"uri": "https://evil/x"})
    assert bad.status_code == 400


def test_device_quartet_profiles(client):
    h = auth_header(login(client, "instructor-alpha")["token"])
    allp = client.get("/api/v1/deviceos/profiles", headers=h)
    assert len(allp.json()["profiles"]) == 4
    for pid in ("student_14_5", "handheld_hybrid", "ds_xl_coder", "edge_io_wearables"):
        r = client.get(f"/api/v1/deviceos/profiles/{pid}", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["capabilities"]["physical_validation"] == "EXTERNAL"
    edge = client.get("/api/v1/deviceos/profiles/edge_io_wearables", headers=h).json()
    assert edge["responsive"]["deep_link_primary"] is True
    assert edge["profile"]["standalone_full_lms"] is False
    coder = client.get("/api/v1/deviceos/profiles/ds_xl_coder", headers=h).json()
    assert coder["profile"]["strongest_learn_to_build"] is True


def test_update_continuity_no_secrets(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    u = client.get("/api/v1/deviceos/update", headers=h)
    assert u.json()["signing_truth"] == "UNSIGNED_DIGITAL_FIXTURE"
    c = client.post(
        "/api/v1/deviceos/continuity",
        headers=h,
        json={
            "from_profile": "handheld_hybrid",
            "to_profile": "student_14_5",
            "lesson_progress": {"lesson": "w01", "pct": 40},
        },
    )
    assert c.status_code == 200
    assert c.json()["contains_secrets"] is False
    bad = client.post(
        "/api/v1/deviceos/continuity",
        headers=h,
        json={
            "from_profile": "a",
            "to_profile": "b",
            "lesson_progress": {"password": "nope"},
        },
    )
    assert bad.status_code == 400
