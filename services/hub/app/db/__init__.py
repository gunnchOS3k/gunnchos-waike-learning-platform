from __future__ import annotations

import sqlite3
from pathlib import Path

from app.migrations.m001_assessment_lifecycle import SQL as M001
from app.migrations.m002_receipt_immutability import SQL as M002


MIGRATIONS: list[tuple[str, str]] = [
    ("001_assessment_lifecycle", M001),
    ("002_receipt_immutability", M002),
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
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        newly.append(version)
    conn.commit()
    return newly
