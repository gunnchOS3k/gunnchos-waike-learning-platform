"""Destructive backup / restore with integrity checks (WAL-safe SQLite backup API)."""

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

# Tables that carry site_id and must be site-filtered for site_admin backups.
SITE_SCOPED_TABLES = frozenset(
    {
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
        "lti_registrations",
        "lti_launches",
        "oneroster_imports",
        "oneroster_entities",
        "qti_imports",
        "continuity_handoffs",
        "backup_manifests",
        "privacy_controls",
        "admin_audit",
        "lti_external_identities",
        "retention_operations",
    }
)

CONTENT_TABLES = [
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return False
    return column in cols


class BackupService:
    def __init__(self, conn: sqlite3.Connection, db_path: str | Path) -> None:
        self.conn = conn
        self.db_path = Path(db_path)

    def _site_filter_connection(self, dst: sqlite3.Connection, site_id: str) -> None:
        """Remove rows that do not belong to site_id from a full DB snapshot."""
        tables = [
            r[0]
            for r in dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table in tables:
            if table == "schema_migrations":
                continue
            if table not in SITE_SCOPED_TABLES and not _table_has_column(dst, table, "site_id"):
                continue
            if not _table_has_column(dst, table, "site_id"):
                continue
            dst.execute(f"DELETE FROM {table} WHERE site_id != ?", (site_id,))
        # Drop orphan LTI state/nonce rows whose registration was removed
        try:
            dst.execute(
                """
                DELETE FROM lti_states WHERE registration_id NOT IN
                  (SELECT registration_id FROM lti_registrations)
                """
            )
            dst.execute(
                """
                DELETE FROM lti_nonces WHERE registration_id NOT IN
                  (SELECT registration_id FROM lti_registrations)
                """
            )
        except sqlite3.Error:
            pass
        dst.commit()

    def _snapshot_content(self, site_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"site_id": site_id, "tables": {}}
        for t in CONTENT_TABLES:
            try:
                if t == "schema_migrations" or not _table_has_column(self.conn, t, "site_id"):
                    rows = self.conn.execute(f"SELECT * FROM {t}").fetchall()
                else:
                    rows = self.conn.execute(
                        f"SELECT * FROM {t} WHERE site_id=?", (site_id,)
                    ).fetchall()
                payload["tables"][t] = [dict(r) for r in rows]
            except sqlite3.Error:
                payload["tables"][t] = []
        return payload

    def create_backup(
        self,
        actor: Actor,
        out_dir: Path | None = None,
        *,
        attachments: list[Path] | None = None,
    ) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("BACKUP_FORBIDDEN", 403)
        out_dir = out_dir or (self.db_path.parent / "backups")
        out_dir.mkdir(parents=True, exist_ok=True)
        backup_id = _id("bak")
        dest = out_dir / f"{backup_id}.waikebak"

        # WAL-safe snapshot via sqlite3 Connection.backup() into a temp file.
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            dst = sqlite3.connect(str(tmp_path))
            try:
                self.conn.backup(dst)
                self._site_filter_connection(dst, actor.site_id)
            finally:
                dst.close()

            content_payload = self._snapshot_content(actor.site_id)
            content_payload["backup_id"] = backup_id
            content_raw = json.dumps(content_payload, sort_keys=True, default=str).encode("utf-8")

            members: list[dict[str, Any]] = []
            hub_bytes = tmp_path.read_bytes()
            members.append(
                {
                    "name": "hub.sqlite3",
                    "size": len(hub_bytes),
                    "sha256": _sha256_bytes(hub_bytes),
                }
            )
            members.append(
                {
                    "name": "content.json",
                    "size": len(content_raw),
                    "sha256": _sha256_bytes(content_raw),
                }
            )

            attachment_blobs: list[tuple[str, bytes]] = []
            for att in attachments or []:
                ap = Path(att)
                if not ap.is_file():
                    raise ServiceError("BACKUP_ATTACHMENT_MISSING", 400)
                data = ap.read_bytes()
                arc = f"attachments/{ap.name}"
                attachment_blobs.append((arc, data))
                members.append(
                    {"name": arc, "size": len(data), "sha256": _sha256_bytes(data)}
                )

            manifest = {
                "backup_id": backup_id,
                "site_id": actor.site_id,
                "created_at": _now(),
                "format": "waikebak-v2",
                "schema_version": "gate-c-closure",
                "members": members,
                # Convenience mirrors for hub + content (also in members table).
                "hub_sqlite3_sha256": members[0]["sha256"],
                "content_sha256": members[1]["sha256"],
            }
            man_raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
            man_sha = _sha256_bytes(man_raw)

            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", man_raw)
                zf.writestr("content.json", content_raw)
                zf.writestr("hub.sqlite3", hub_bytes)
                for arc, data in attachment_blobs:
                    zf.writestr(arc, data)

            self.conn.execute(
                """
                INSERT INTO backup_manifests(
                  backup_id, site_id, actor_id, manifest_sha256, content_sha256, path, created_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    backup_id,
                    actor.site_id,
                    actor.actor_id,
                    man_sha,
                    members[1]["sha256"],
                    str(dest),
                    _now(),
                ),
            )
            for m in members:
                self.conn.execute(
                    """
                    INSERT INTO backup_member_hashes(backup_id, member_name, size_bytes, sha256)
                    VALUES (?,?,?,?)
                    """,
                    (backup_id, m["name"], m["size"], m["sha256"]),
                )
            _audit(
                self.conn,
                actor.actor_id,
                "backup.create",
                "backup",
                backup_id,
                {"sha": members[1]["sha256"], "hub_sha": members[0]["sha256"]},
            )
            self.conn.commit()
            return {
                "backup_id": backup_id,
                "path": str(dest),
                "manifest_sha256": man_sha,
                "content_sha256": members[1]["sha256"],
                "hub_sqlite3_sha256": members[0]["sha256"],
                "members": members,
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    def verify_archive(self, path: Path, *, expected_site_id: str | None = None) -> dict[str, Any]:
        if not path.is_file():
            raise ServiceError("BACKUP_NOT_FOUND", 404)
        if path.stat().st_size > MAX_BACKUP_BYTES:
            raise ServiceError("BACKUP_TOO_LARGE", 400)
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            raise ServiceError("BACKUP_BAD_ARCHIVE", 400) from e
        names = set(zf.namelist())
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ServiceError("BACKUP_TRAVERSAL", 400)
        try:
            man = json.loads(zf.read("manifest.json"))
        except (KeyError, OSError, json.JSONDecodeError) as e:
            raise ServiceError("BACKUP_INCOMPLETE", 400) from e

        members = man.get("members")
        if not isinstance(members, list) or not members:
            # Legacy v1: at least content hash
            if "content.json" not in names:
                raise ServiceError("BACKUP_INCOMPLETE", 400)
            content = zf.read("content.json")
            calc = _sha256_bytes(content)
            if calc != man.get("content_sha256"):
                raise ServiceError("BACKUP_TAMPER", 400)
            if "hub.sqlite3" in names and man.get("hub_sqlite3_sha256"):
                hub = zf.read("hub.sqlite3")
                if _sha256_bytes(hub) != man["hub_sqlite3_sha256"]:
                    raise ServiceError("BACKUP_TAMPER", 400)
            return {"ok": True, "manifest": man, "content_sha256": calc}

        required = {"hub.sqlite3", "content.json"}
        member_names = {m.get("name") for m in members if isinstance(m, dict)}
        if not required.issubset(member_names):
            raise ServiceError("BACKUP_INCOMPLETE", 400)
        for m in members:
            name = m.get("name")
            if not name or name not in names:
                raise ServiceError("BACKUP_INCOMPLETE", 400)
            data = zf.read(name)
            if len(data) != int(m.get("size", -1)):
                raise ServiceError("BACKUP_TAMPER", 400)
            if _sha256_bytes(data) != m.get("sha256"):
                raise ServiceError("BACKUP_TAMPER", 400)

        # Explicit hub.sqlite3 mismatch is a hard fail (even if members list omitted it).
        hub = zf.read("hub.sqlite3")
        hub_sha = _sha256_bytes(hub)
        claimed_hub = man.get("hub_sqlite3_sha256") or next(
            (m["sha256"] for m in members if m.get("name") == "hub.sqlite3"), None
        )
        if claimed_hub and hub_sha != claimed_hub:
            raise ServiceError("BACKUP_TAMPER", 400)

        if expected_site_id is not None and man.get("site_id") != expected_site_id:
            raise ServiceError("BACKUP_CROSS_SITE", 403)

        content_sha = next(
            (m["sha256"] for m in members if m.get("name") == "content.json"),
            man.get("content_sha256"),
        )
        return {"ok": True, "manifest": man, "content_sha256": content_sha, "hub_sqlite3_sha256": hub_sha}

    def destructive_restore(self, actor: Actor, path: Path) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("BACKUP_FORBIDDEN", 403)
        verified = self.verify_archive(path, expected_site_id=actor.site_id)
        man = verified["manifest"]
        # Schema mismatch: refuse archives that claim an incompatible format without hub
        if man.get("format") not in {"waikebak-v1", "waikebak-v2", None}:
            raise ServiceError("BACKUP_SCHEMA_MISMATCH", 400)

        with zipfile.ZipFile(path) as zf:
            if "hub.sqlite3" not in zf.namelist():
                raise ServiceError("BACKUP_INCOMPLETE", 400)
            with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
                tmp.write(zf.read("hub.sqlite3"))
                tmp_path = Path(tmp.name)

        # Cross-site refuse: restored DB must only contain actor's site (or empty others)
        probe = sqlite3.connect(str(tmp_path))
        probe.row_factory = sqlite3.Row
        try:
            if _table_has_column(probe, "users", "site_id"):
                foreign = probe.execute(
                    "SELECT 1 FROM users WHERE site_id != ? LIMIT 1", (actor.site_id,)
                ).fetchone()
                if foreign is not None:
                    probe.close()
                    tmp_path.unlink(missing_ok=True)
                    raise ServiceError("BACKUP_CROSS_SITE", 403)
            # Schema sanity: schema_migrations must exist
            try:
                probe.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
            except sqlite3.Error as e:
                probe.close()
                tmp_path.unlink(missing_ok=True)
                raise ServiceError("BACKUP_SCHEMA_MISMATCH", 400) from e
        finally:
            probe.close()

        self.conn.close()
        shutil.copy2(tmp_path, self.db_path)
        tmp_path.unlink(missing_ok=True)
        new_conn = connect(self.db_path)
        applied = migrate(new_conn)
        self.conn = new_conn
        return {
            "status": "restored",
            "manifest": verified["manifest"],
            "migrations_applied": applied,
            "destructive": True,
        }
