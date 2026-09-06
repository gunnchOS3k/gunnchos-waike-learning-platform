"""Destructive backup / restore with integrity checks."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.auth import Actor
from app.db import connect, migrate
from app.modules.assessment_lifecycle import ServiceError, _audit, _id, _now

MAX_BACKUP_BYTES = 50_000_000


class BackupService:
    def __init__(self, conn: sqlite3.Connection, db_path: str | Path) -> None:
        self.conn = conn
        self.db_path = Path(db_path)

    def create_backup(self, actor: Actor, out_dir: Path | None = None) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("BACKUP_FORBIDDEN", 403)
        out_dir = out_dir or (self.db_path.parent / "backups")
        out_dir.mkdir(parents=True, exist_ok=True)
        backup_id = _id("bak")
        dest = out_dir / f"{backup_id}.waikebak"
        # Snapshot critical tables
        tables = [
            "users",
            "role_assignments",
            "sections",
            "enrollments",
            "submission_receipts",
            "grades",
            "quiz_definitions",
            "quiz_items",
            "quiz_attempts",
            "audit_events",
            "schema_migrations",
        ]
        payload: dict[str, Any] = {"backup_id": backup_id, "site_id": actor.site_id, "tables": {}}
        for t in tables:
            try:
                rows = self.conn.execute(f"SELECT * FROM {t}").fetchall()
                payload["tables"][t] = [dict(r) for r in rows]
            except sqlite3.Error:
                payload["tables"][t] = []
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        content_sha = hashlib.sha256(raw).hexdigest()
        manifest = {
            "backup_id": backup_id,
            "content_sha256": content_sha,
            "site_id": actor.site_id,
            "created_at": _now(),
            "format": "waikebak-v1",
        }
        man_raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
        man_sha = hashlib.sha256(man_raw).hexdigest()
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", man_raw)
            zf.writestr("content.json", raw)
            # Copy DB file bytes for destructive restore path
            if self.db_path.is_file():
                zf.write(self.db_path, arcname="hub.sqlite3")
        self.conn.execute(
            """
            INSERT INTO backup_manifests(
              backup_id, site_id, actor_id, manifest_sha256, content_sha256, path, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (backup_id, actor.site_id, actor.actor_id, man_sha, content_sha, str(dest), _now()),
        )
        _audit(self.conn, actor.actor_id, "backup.create", "backup", backup_id, {"sha": content_sha})
        self.conn.commit()
        return {
            "backup_id": backup_id,
            "path": str(dest),
            "manifest_sha256": man_sha,
            "content_sha256": content_sha,
        }

    def verify_archive(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ServiceError("BACKUP_NOT_FOUND", 404)
        if path.stat().st_size > MAX_BACKUP_BYTES:
            raise ServiceError("BACKUP_TOO_LARGE", 400)
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            raise ServiceError("BACKUP_BAD_ARCHIVE", 400) from e
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ServiceError("BACKUP_TRAVERSAL", 400)
        try:
            man = json.loads(zf.read("manifest.json"))
            content = zf.read("content.json")
        except (KeyError, OSError, json.JSONDecodeError) as e:
            raise ServiceError("BACKUP_INCOMPLETE", 400) from e
        calc = hashlib.sha256(content).hexdigest()
        if calc != man.get("content_sha256"):
            raise ServiceError("BACKUP_TAMPER", 400)
        return {"ok": True, "manifest": man, "content_sha256": calc}

    def destructive_restore(self, actor: Actor, path: Path) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("BACKUP_FORBIDDEN", 403)
        verified = self.verify_archive(path)
        with zipfile.ZipFile(path) as zf:
            if "hub.sqlite3" not in zf.namelist():
                raise ServiceError("BACKUP_INCOMPLETE", 400)
            with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
                tmp.write(zf.read("hub.sqlite3"))
                tmp_path = Path(tmp.name)
        # Replace live DB file (destructive)
        self.conn.close()
        shutil.copy2(tmp_path, self.db_path)
        tmp_path.unlink(missing_ok=True)
        # Reopen + migrate forward if needed
        new_conn = connect(self.db_path)
        applied = migrate(new_conn)
        self.conn = new_conn
        return {
            "status": "restored",
            "manifest": verified["manifest"],
            "migrations_applied": applied,
            "destructive": True,
        }
