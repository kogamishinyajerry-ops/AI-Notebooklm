from __future__ import annotations

import sqlite3
from typing import Callable

from core.storage.migrations import v4_2_t5_fk_enforcement


MigrationFn = Callable[[sqlite3.Connection], None]
_PENDING_MIGRATIONS: tuple[tuple[int, MigrationFn], ...] = (
    (v4_2_t5_fk_enforcement.VERSION, v4_2_t5_fk_enforcement.apply),
)


def get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version={int(version)}")


def apply_pending(conn: sqlite3.Connection) -> None:
    current_version = get_user_version(conn)
    for target_version, migration in _PENDING_MIGRATIONS:
        if current_version >= target_version:
            continue
        migration(conn)
        set_user_version(conn, target_version)
        current_version = target_version
