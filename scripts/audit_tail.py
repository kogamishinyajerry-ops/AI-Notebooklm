from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print the most recent audit log rows.")
    parser.add_argument(
        "--db",
        default="data/notebooks.db",
        help="Path to the SQLite database (default: data/notebooks.db).",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=100,
        help="How many rows to print (default: 100).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM audit_events
            ORDER BY ts_utc DESC, event_id DESC
            LIMIT ?
            """,
            (args.last,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
