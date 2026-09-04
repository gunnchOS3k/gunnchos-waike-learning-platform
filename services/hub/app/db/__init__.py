from __future__ import annotations

import sqlite3
from pathlib import Path

from app.migrations.m001_assessment_lifecycle import SQL as M001
from app.migrations.m002_receipt_immutability import SQL as M002
from app.migrations.m003_identity_sections_gradebook import SQL as M003


MIGRATIONS: list[tuple[str, str]] = [
    ("001_assessment_lifecycle", M001),
    ("002_receipt_immutability", M002),
    ("003_identity_sections_gradebook", M003),
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
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
