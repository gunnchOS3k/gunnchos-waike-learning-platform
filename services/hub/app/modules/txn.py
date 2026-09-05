"""Savepoint depth tracking so an inner service cannot commit an outer mutation away.

``sqlite3.Connection`` supports neither attributes nor weak references, so depth is keyed
by ``id(conn)`` and the entry is removed once it returns to zero, which keeps a recycled
id from inheriting a stale depth.
"""

from __future__ import annotations

import sqlite3

_DEPTH: dict[int, int] = {}


def depth(conn: sqlite3.Connection) -> int:
    return _DEPTH.get(id(conn), 0)


def enter(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(f"SAVEPOINT {name}")
    _DEPTH[id(conn)] = depth(conn) + 1


def release(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(f"RELEASE SAVEPOINT {name}")
    _pop(conn)


def rollback(conn: sqlite3.Connection, name: str) -> None:
    """Undo everything inside the savepoint and release it."""
    conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
    conn.execute(f"RELEASE SAVEPOINT {name}")
    _pop(conn)


def commit(conn: sqlite3.Connection) -> None:
    """Commit only at the outermost level; a nested commit would destroy live savepoints."""
    if depth(conn) == 0:
        conn.commit()


def _pop(conn: sqlite3.Connection) -> None:
    key = id(conn)
    current = _DEPTH.get(key, 0) - 1
    if current > 0:
        _DEPTH[key] = current
    else:
        _DEPTH.pop(key, None)
