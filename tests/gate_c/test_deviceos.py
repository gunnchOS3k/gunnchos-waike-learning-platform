"""Device OS bridge + profiles + deep links + continuity.

Gate C requires DEVICE_OS_ROOT so live Device OS modules are exercised.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from helpers import auth_header, login


def _device_os_root() -> Path | None:
    env = os.environ.get("DEVICE_OS_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    sibling = Path(__file__).resolve().parents[3].parent / "gunnchos-device-os"
    if sibling.is_dir() and (sibling / "gunnchos_device_os").is_dir():
        return sibling
    return None


@pytest.fixture(scope="module", autouse=True)
def _ensure_device_os_env():
    """Prefer fail in gate_c when Device OS is missing; set env if sibling checkout exists."""
    root = _device_os_root()
    if root is None:
        pytest.fail(
            "DEVICE_OS_ROOT missing — Gate C deviceos tests require a Device OS checkout "
            "(set DEVICE_OS_ROOT or place gunnchos-device-os as a sibling workspace)."
        )
    os.environ.setdefault("DEVICE_OS_ROOT", str(root))
    # Reset cached imports in case prior tests ran without root
    import app.modules.deviceos_bridge as bridge

    bridge._DEVICE_OS_IMPORTS = None


def test_manifest_and_contracts(client):
    h = auth_header(login(client, "learner-alpha")["token"])
    m = client.get("/api/v1/deviceos/manifest", headers=h)
    assert m.status_code == 200
    body = m.json()
    assert body["app_id"] == "com.gunnchos.waike.learning"
    assert body["device_os_registry_id"] == "waike_learning_os"
    assert body["device_os_live_imports"] is True
    assert body["launcher_wrapper_relationship"] == "thin_launcher_companion"
    c = client.get("/api/v1/deviceos/contracts", headers=h)
    assert c.status_code == 200
    paths = c.json()["paths"]
    assert "launcher" in paths
    assert "learning_os_launcher" in paths
    assert c.json()["device_os_live_imports"] is True
    assert c.json()["registry_sample"]["canonical"] == "waike_learning_os"
    assert c.json()["registry_sample"]["alias_resolves_to"] == "waike_learning_os"


def test_launcher_permissions(client):
    h = auth_header(login(client, "learner-alpha")["token"])
    la = client.get("/api/v1/deviceos/launcher", headers=h)
    assert la.status_code == 200
    body = la.json()
    assert body["authority"] == "device_os"
    assert body["launched_via"] == "device_os_learning_os_launcher"
    assert body["relationship"] == "thin_launcher_companion"
    assert body["seed_is_system_of_record"] is False
    assert body["system_of_record"] == "platform_tauri_learning_os"
    assert body["handoff"]["bundle_id"] == "com.gunnchos.waike.learning"
    p = client.get("/api/v1/deviceos/permissions", headers=h)
    assert p.status_code == 200
    perms = p.json()
    assert "files_read" in perms["allowed"]
    assert "ai_cloud_export" in perms["denied"]
    assert perms["authority"] == "device_os_permissions_manager"
    assert perms["device_os_role"] == "student"
    assert perms["device_os_sample_grant"]["decision"] == "allow"


def test_deep_link_requires_auth_and_rejects_bypass(client):
    r = client.post("/api/v1/deviceos/deep-link", json={"uri": "waike://learn/home"})
    assert r.status_code in {401, 403}
    h = auth_header(login(client, "learner-alpha")["token"])
    ok = client.post("/api/v1/deviceos/deep-link", headers=h, json={"uri": "waike://learn/home"})
    assert ok.status_code == 200
    assert ok.json()["auth_bypassed"] is False
    assert ok.json()["device_os_validated"] is True
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
        assert r.json()["fixture_label"] == "device_quartet_digital_fixture_only"
    edge = client.get("/api/v1/deviceos/profiles/edge_io_wearables", headers=h).json()
    assert edge["responsive"]["deep_link_primary"] is True
    assert edge["profile"]["standalone_full_lms"] is False
    coder = client.get("/api/v1/deviceos/profiles/ds_xl_coder", headers=h).json()
    assert coder["profile"]["strongest_learn_to_build"] is True


def test_update_continuity_no_secrets(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    u = client.get("/api/v1/deviceos/update", headers=h)
    assert u.status_code == 200
    assert u.json()["signing_truth"] == "UNSIGNED_DIGITAL_FIXTURE"
    assert u.json()["authority"] == "device_os_updater"
    assert u.json()["rollback_probe"]["success"] is True
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
    assert c.json().get("continuity_owner") == "device_os_continuity_coordinator"
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
