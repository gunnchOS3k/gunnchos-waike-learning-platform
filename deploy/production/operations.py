#!/usr/bin/env python3
"""Host-operator maintenance for the EXISTING Hub database and blob directory.

All operations require the server to be stopped (exclusive shared lock). Restore
only targets a new empty data directory; switching the volume is deliberate.
Snapshots contain private records: store on encrypted, access-controlled media.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/hub'))
from app.db import connect, migrate, MIGRATIONS


def sha(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def stopped(data_dir):
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (data_dir / '.hub.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('HUB_RUNNING_STOP_BEFORE_MAINTENANCE') from exc
        yield


def verify_database(path):
    if not Path(path).is_file():
        raise ValueError('HUB_DATABASE_MISSING')
    conn = sqlite3.connect(path)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLITE_INTEGRITY_FAILED')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('SQLITE_FOREIGN_KEY_CHECK_FAILED')
        return [r[0] for r in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    finally:
        conn.close()


def backup(data_dir: Path, out: Path):
    if out.exists() or out.resolve().is_relative_to(data_dir.resolve()):
        raise ValueError('BACKUP_REQUIRES_NEW_EXTERNAL_FILE')
    with stopped(data_dir), tempfile.TemporaryDirectory() as temp:
        source = data_dir / 'hub.sqlite3'
        if not source.is_file():
            raise ValueError('HUB_DATABASE_MISSING')
        snapshot = Path(temp) / 'hub.sqlite3'
        src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
        dst = sqlite3.connect(snapshot)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        versions = verify_database(snapshot)
        files = {'hub.sqlite3': snapshot.read_bytes()}
        for path in sorted((data_dir / 'blobs').rglob('*')):
            if path.is_symlink():
                raise ValueError('BLOB_SYMLINK_FORBIDDEN')
            if path.is_file():
                files[path.relative_to(data_dir).as_posix()] = path.read_bytes()
        manifest = dict(format='waike-host-snapshot-v1', schema_versions=versions, members={name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in files.items()})
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as target, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        return dict(snapshot=str(out), sha256=sha(out.read_bytes()), schema_versions=versions, files=len(files))


def restore(snapshot: Path, data_dir: Path):
    if data_dir.exists() and any(data_dir.iterdir()):
        raise ValueError('RESTORE_REQUIRES_EMPTY_DIRECTORY')
    with zipfile.ZipFile(snapshot) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'waike-host-snapshot-v1':
            raise ValueError('SNAPSHOT_FORMAT_MISMATCH')
        members = manifest['members']
        if set(archive.namelist()) != set(members) | {'manifest.json'} or 'hub.sqlite3' not in members:
            raise ValueError('SNAPSHOT_MEMBERS_MISMATCH')
        verified = {}
        for name, record in members.items():
            parts = Path(name).parts
            if Path(name).is_absolute() or '..' in parts or not (name == 'hub.sqlite3' or name.startswith('blobs/')) or '\\' in name:
                raise ValueError('SNAPSHOT_PATH_FORBIDDEN')
            raw = archive.read(name)
            if len(raw) != record['bytes'] or sha(raw) != record['sha256']:
                raise ValueError('SNAPSHOT_HASH_MISMATCH')
            verified[name] = raw
        # Validate before writing into the destination. Never extractall().
        with tempfile.TemporaryDirectory() as temp:
            probe = Path(temp) / 'hub.sqlite3'; probe.write_bytes(verified['hub.sqlite3'])
            versions = verify_database(probe)
            if versions != manifest['schema_versions']:
                raise ValueError('SNAPSHOT_SCHEMA_MISMATCH')
        with stopped(data_dir):
            for name, raw in verified.items():
                target = data_dir / name
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(raw)
        return dict(restored=str(data_dir), schema_versions=versions, files=len(verified))


def migration(data_dir: Path, backup_path: Path | None):
    db = data_dir / 'hub.sqlite3'
    snapshot = backup(data_dir, backup_path) if db.exists() and backup_path else None
    if db.exists() and not backup_path:
        raise ValueError('EXISTING_DATABASE_REQUIRES_BACKUP')
    with stopped(data_dir):
        if db.exists():
            # Rehearse against the exact snapshot before touching the stopped DB.
            with tempfile.TemporaryDirectory() as temp:
                restored = Path(temp) / 'rehearsal'
                restore(backup_path, restored)
                probe = connect(restored / 'hub.sqlite3')
                migrate(probe); probe.close()
                if verify_database(restored / 'hub.sqlite3') != [v for v, _ in MIGRATIONS]:
                    raise ValueError('UNEXPECTED_SCHEMA_VERSIONS')
        conn = connect(db)
        applied = migrate(conn); conn.close()
        versions = verify_database(db)
        if versions != [v for v, _ in MIGRATIONS]:
            raise ValueError('UNEXPECTED_SCHEMA_VERSIONS')
        os.chmod(db, 0o600)
        return dict(migrations_applied=applied, schema_versions=versions, backup=snapshot, rehearsal_verified=bool(snapshot))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore', 'migrate', 'verify'])
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    if args.action in {'backup', 'restore'} and not args.snapshot:
        parser.error('--snapshot required')
    if args.action == 'backup': result = backup(args.data_dir, args.snapshot)
    elif args.action == 'restore': result = restore(args.snapshot, args.data_dir)
    elif args.action == 'migrate': result = migration(args.data_dir, args.snapshot)
    else:
        with stopped(args.data_dir): result = dict(schema_versions=verify_database(args.data_dir / 'hub.sqlite3'))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
