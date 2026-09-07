"""Backup / restore integrity."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.modules.assessment_lifecycle import ServiceError
from helpers import auth_header, login


def _enable_export(client, h):
    client.put(
        "/api/v1/privacy/controls",
        headers=h,
        json={
            "youth_mode": False,
            "data_minimization": True,
            "export_allowed": True,
            "retention_days": 365,
        },
    )


def _admin_actor(site_id: str = "site-alpha", actor_id: str = "admin-alpha"):
    return type(
        "A",
        (),
        {"is_site_admin": True, "actor_id": actor_id, "site_id": site_id},
    )()


def test_backup_and_tamper(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    r = client.post("/api/v1/admin/backup", headers=h)
    assert r.status_code == 200, r.text
    path = Path(r.json()["path"])
    assert path.is_file()
    members = r.json().get("members")
    assert isinstance(members, list) and members, "backup response must include members"
    assert any(
        isinstance(m, dict) and m.get("name") == "hub.sqlite3" for m in members
    ), "backup members must include hub.sqlite3"

    evil = tmp_path / "evil.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(evil, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        content = json.loads(src.read("content.json"))
        content["tampered"] = True
        raw = json.dumps(content).encode()
        dst.writestr("manifest.json", json.dumps(man))
        dst.writestr("content.json", raw)
        if "hub.sqlite3" in src.namelist():
            dst.writestr("hub.sqlite3", src.read("hub.sqlite3"))
    try:
        client.app.state.backup.verify_archive(evil)
        assert False
    except ServiceError as e:
        assert e.code in {"BACKUP_TAMPER", "BACKUP_BAD_ARCHIVE", "BACKUP_INCOMPLETE"}


def test_backup_db_integrity_member_hashes(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    bak = client.post("/api/v1/admin/backup", headers=h).json()
    path = Path(bak["path"])
    with zipfile.ZipFile(path) as zf:
        man = json.loads(zf.read("manifest.json"))
        members = {m["name"]: m for m in man["members"]}
        assert "hub.sqlite3" in members
        assert "content.json" in members
        hub = zf.read("hub.sqlite3")
        import hashlib

        assert hashlib.sha256(hub).hexdigest() == members["hub.sqlite3"]["sha256"]
        assert bak["hub_sqlite3_sha256"] == members["hub.sqlite3"]["sha256"]


def test_tamper_hub_sqlite_detected(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    path = Path(client.post("/api/v1/admin/backup", headers=h).json()["path"])
    evil = tmp_path / "hub-tamper.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(evil, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        dst.writestr("manifest.json", json.dumps(man))
        dst.writestr("content.json", src.read("content.json"))
        dst.writestr("hub.sqlite3", src.read("hub.sqlite3") + b"\x00SABOTAGE")
    try:
        client.app.state.backup.verify_archive(evil)
        assert False
    except ServiceError as e:
        assert e.code == "BACKUP_TAMPER"


def test_missing_member(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    path = Path(client.post("/api/v1/admin/backup", headers=h).json()["path"])
    incomplete = tmp_path / "incomplete.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(incomplete, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        dst.writestr("manifest.json", json.dumps(man))
        dst.writestr("content.json", src.read("content.json"))
        # omit hub.sqlite3
    try:
        client.app.state.backup.verify_archive(incomplete)
        assert False
    except ServiceError as e:
        assert e.code in {"BACKUP_INCOMPLETE", "BACKUP_TAMPER"}


def test_destructive_restore(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    bak = client.post("/api/v1/admin/backup", headers=h).json()
    path = Path(bak["path"])
    pre = client.app.state.db.execute(
        "SELECT display_name FROM users WHERE username='learner-alpha'"
    ).fetchone()["display_name"]
    client.app.state.db.execute(
        "UPDATE users SET display_name='MUTATED' WHERE username='learner-alpha'"
    )
    client.app.state.db.commit()
    result = client.app.state.backup.destructive_restore(_admin_actor(), path)
    client.app.state.db = client.app.state.backup.conn
    row = client.app.state.db.execute(
        "SELECT display_name FROM users WHERE username='learner-alpha'"
    ).fetchone()
    assert row["display_name"] == pre
    assert result["destructive"] is True
    assert result["status"] == "restored"


def test_destructive_restore_via_api(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    bak = client.post("/api/v1/admin/backup", headers=h).json()
    path = bak["path"]
    pre = client.app.state.db.execute(
        "SELECT display_name FROM users WHERE username='learner-alpha'"
    ).fetchone()["display_name"]
    client.app.state.db.execute(
        "UPDATE users SET display_name='MUTATED_API' WHERE username='learner-alpha'"
    )
    client.app.state.db.commit()
    r = client.post("/api/v1/admin/restore", headers=h, json={"path": path})
    assert r.status_code == 200, r.text
    row = client.app.state.db.execute(
        "SELECT display_name FROM users WHERE username='learner-alpha'"
    ).fetchone()
    assert row["display_name"] == pre


def test_cross_site_restore_refused(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    path = Path(client.post("/api/v1/admin/backup", headers=h).json()["path"])
    # Rewrite manifest site_id to beta while keeping hashes of members
    evil = tmp_path / "cross.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(evil, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        man["site_id"] = "site-beta"
        dst.writestr("manifest.json", json.dumps(man, sort_keys=True))
        for name in ("content.json", "hub.sqlite3"):
            dst.writestr(name, src.read(name))
    try:
        client.app.state.backup.destructive_restore(_admin_actor("site-alpha"), evil)
        assert False
    except ServiceError as e:
        assert e.code == "BACKUP_CROSS_SITE"


def test_schema_mismatch(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    _enable_export(client, h)
    path = Path(client.post("/api/v1/admin/backup", headers=h).json()["path"])
    bad = tmp_path / "schema.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(bad, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        man["format"] = "waikebak-v999-incompatible"
        # Recompute is not needed — restore checks format before trusting
        content = src.read("content.json")
        hub = src.read("hub.sqlite3")
        import hashlib

        members = [
            {"name": "hub.sqlite3", "size": len(hub), "sha256": hashlib.sha256(hub).hexdigest()},
            {
                "name": "content.json",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        ]
        man["members"] = members
        man["hub_sqlite3_sha256"] = members[0]["sha256"]
        man["content_sha256"] = members[1]["sha256"]
        dst.writestr("manifest.json", json.dumps(man, sort_keys=True))
        dst.writestr("content.json", content)
        dst.writestr("hub.sqlite3", hub)
    try:
        client.app.state.backup.destructive_restore(_admin_actor(), bad)
        assert False
    except ServiceError as e:
        assert e.code == "BACKUP_SCHEMA_MISMATCH"
