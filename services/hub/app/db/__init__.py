from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.migrations.m001_assessment_lifecycle import SQL as M001
from app.migrations.m002_receipt_immutability import SQL as M002
from app.migrations.m003_identity_sections_gradebook import SQL as M003
from app.migrations.m004_offline_sync_activities import SQL as M004
from app.migrations.m005_ai_policy import SQL as M005
from app.migrations.m006_gate_c import SQL as M006
from app.migrations.m007_gate_c_owner import SQL as M007
from app.migrations.m008_gate_d import SQL as M008
from app.migrations.m009_learner_product import SQL as M009


MIGRATIONS: list[tuple[str, str]] = [
    ("001_assessment_lifecycle", M001),
    ("002_receipt_immutability", M002),
    ("003_identity_sections_gradebook", M003),
    ("004_offline_sync_activities", M004),
    ("005_ai_policy", M005),
    ("006_gate_c", M006),
    ("007_gate_c_owner", M007),
    ("008_gate_d", M008),
    ("009_learner_product", M009),
]


class _LockedRows:
    """Holds the connection lock until the caller reads the result."""

    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock
        self._open = True

    def _release(self) -> None:
        if self._open:
            self._open = False
            self._lock.release()

    def fetchone(self):
        try:
            return self._cursor.fetchone()
        finally:
            self._release()

    def fetchall(self):
        try:
            return self._cursor.fetchall()
        finally:
            self._release()

    def __iter__(self):
        try:
            yield from self._cursor
        finally:
            self._release()

    def __del__(self) -> None:
        self._release()


class SerializedConnection(sqlite3.Connection):
    """One Hub connection is shared by FastAPI's threadpool. Serialize it."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()

    def execute(self, sql, parameters=()):  # type: ignore[override]
        self._lock.acquire()
        try:
            cursor = super().execute(sql, parameters)
        except Exception:
            self._lock.release()
            raise
        head = str(sql).lstrip().split(None, 1)[0].upper() if str(sql).strip() else ""
        if head in {"SELECT", "WITH", "PRAGMA"}:
            return _LockedRows(cursor, self._lock)
        self._lock.release()
        return cursor

    def executemany(self, sql, seq):  # type: ignore[override]
        with self._lock:
            return super().executemany(sql, seq)

    def executescript(self, sql):  # type: ignore[override]
        with self._lock:
            return super().executescript(sql)

    def commit(self):  # type: ignore[override]
        with self._lock:
            return super().commit()

    def rollback(self):  # type: ignore[override]
        with self._lock:
            return super().rollback()


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, factory=SerializedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    newly: list[str] = []
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        # ALTER TABLE ADD COLUMN may fail if column already exists on re-run of partial scripts;
        # wrap statements carefully via executescript for full migration bodies.
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column" in msg:
                # Continue applying remaining CREATE TABLE statements by splitting.
                for stmt in sql.split(";"):
                    s = stmt.strip()
                    if not s:
                        continue
                    try:
                        conn.execute(s)
                    except sqlite3.OperationalError as inner:
                        if "duplicate column" not in str(inner).lower():
                            raise
            else:
                raise
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        newly.append(version)
    conn.commit()
    return newly
