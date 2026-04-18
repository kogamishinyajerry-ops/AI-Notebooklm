from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path


_DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS audit_events_no_update;
DROP TRIGGER IF EXISTS audit_events_no_delete;
"""

_CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune old rows from audit_events.")
    parser.add_argument(
        "--db",
        default="data/notebooks.db",
        help="Path to the SQLite database (default: data/notebooks.db).",
    )
    parser.add_argument(
        "--before",
        required=True,
        help="Delete rows with ts_utc dates before YYYY-MM-DD.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required safety flag; without it the script exits without changes.",
    )
    return parser.parse_args()


def _validate_before(raw: str) -> str:
    return date.fromisoformat(raw).isoformat()


def main() -> int:
    args = _parse_args()
    if not args.confirm:
        raise SystemExit("Refusing to prune without --confirm.")

    before_date = _validate_before(args.before)
    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executescript(_DROP_TRIGGERS)
        conn.execute(
            """
            DELETE FROM audit_events
            WHERE substr(ts_utc, 1, 10) < ?
            """,
            (before_date,),
        )
        deleted = conn.execute("SELECT changes()").fetchone()[0]
        conn.executescript(_CREATE_TRIGGERS)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Deleted {deleted} audit rows before {before_date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
