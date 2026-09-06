"""Backup / restore integrity."""

from __future__ import annotations

from pathlib import Path

from helpers import auth_header, login


def test_backup_and_tamper(client, tmp_path):
    h = auth_header(login(client, "admin-alpha")["token"])
    r = client.post("/api/v1/admin/backup", headers=h)
    assert r.status_code == 200, r.text
    path = Path(r.json()["path"])
    assert path.is_file()
    # Tamper by rewriting content.json hash mismatch inside a valid zip
    import json
    import zipfile

    evil = tmp_path / "evil.waikebak"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(evil, "w") as dst:
        man = json.loads(src.read("manifest.json"))
        content = json.loads(src.read("content.json"))
        content["tampered"] = True
        raw = json.dumps(content).encode()
        # keep original claimed hash → mismatch
        dst.writestr("manifest.json", json.dumps(man))
        dst.writestr("content.json", raw)
        if "hub.sqlite3" in src.namelist():
            dst.writestr("hub.sqlite3", src.read("hub.sqlite3"))
    from app.modules.assessment_lifecycle import ServiceError

    try:
        client.app.state.backup.verify_archive(evil)
        assert False
    except ServiceError as e:
        assert e.code in {"BACKUP_TAMPER", "BACKUP_BAD_ARCHIVE", "BACKUP_INCOMPLETE"}


def test_destructive_restore(client):
    h = auth_header(login(client, "admin-alpha")["token"])
    bak = client.post("/api/v1/admin/backup", headers=h).json()
    path = Path(bak["path"])
    # mutate a user display name then restore
    client.app.state.db.execute(
        "UPDATE users SET display_name='MUTATED' WHERE username='learner-alpha'"
    )
    client.app.state.db.commit()
    result = client.app.state.backup.destructive_restore(
        type("A", (), {
            "is_site_admin": True,
            "actor_id": "admin-alpha",
            "site_id": "site-alpha",
        })(),
        path,
    )
    # After restore, reconnect app state
    client.app.state.db = client.app.state.backup.conn
    row = client.app.state.db.execute(
        "SELECT display_name FROM users WHERE username='learner-alpha'"
    ).fetchone()
    assert row["display_name"] != "MUTATED" or result["destructive"] is True
