from __future__ import annotations

import sqlite3


VERSION = 1


def apply(conn: sqlite3.Connection) -> None:
    """Step 2 scaffold for the T5 FK-enforcement migration.

    The real table-rebuild logic is filled in during Step 5. For now this
    migration is intentionally a no-op so we can wire user_version plumbing
    and idempotence tests without changing runtime behavior yet.
    """
    del conn
