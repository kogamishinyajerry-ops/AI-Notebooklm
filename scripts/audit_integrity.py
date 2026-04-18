from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.governance.audit_events import AuditEvent
from core.governance.audit_logger import AuditLogger


@dataclass(frozen=True)
class OrphanRelation:
    table: str
    id_column: str
    parent_table: str = "notebooks"
    parent_column: str = "id"
    fk_column: str = "notebook_id"


ORPHAN_RELATIONS: tuple[OrphanRelation, ...] = (
    OrphanRelation(table="notes", id_column="id"),
    OrphanRelation(table="sources", id_column="id"),
    OrphanRelation(table="chat_messages", id_column="id"),
    OrphanRelation(table="studio_outputs", id_column="id"),
    OrphanRelation(table="knowledge_graphs", id_column="notebook_id"),
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check and repair orphan SQLite rows covered by notebook FK constraints.",
    )
    parser.add_argument(
        "--db",
        default="data/notebooks.db",
        help="Path to the SQLite database (default: data/notebooks.db).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Scan only; exit 1 if orphans exist.")
    mode.add_argument("--repair", action="store_true", help="Delete detected orphans.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-interactive repair.",
    )
    return parser.parse_args(argv)


def _open_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone()
    return row is not None


def _iter_orphan_ids(
    conn: sqlite3.Connection,
    relation: OrphanRelation,
) -> list[str]:
    if not _table_exists(conn, relation.table):
        return []
    rows = conn.execute(
        f"""
        SELECT child.{relation.id_column} AS orphan_id
        FROM {relation.table} AS child
        LEFT JOIN {relation.parent_table} AS parent
          ON child.{relation.fk_column} = parent.{relation.parent_column}
        WHERE parent.{relation.parent_column} IS NULL
        ORDER BY child.{relation.id_column}
        """
    ).fetchall()
    return [str(row["orphan_id"]) for row in rows]


def scan_orphans(db_path: str | Path) -> dict[str, list[str]]:
    path = Path(db_path)
    conn = _open_connection(path)
    try:
        return {
            relation.table: _iter_orphan_ids(conn, relation)
            for relation in ORPHAN_RELATIONS
        }
    finally:
        conn.close()


def _print_counts(orphan_ids: dict[str, list[str]]) -> None:
    total = 0
    for table in sorted(orphan_ids):
        count = len(orphan_ids[table])
        total += count
        print(f"{table}: {count}")
    print(f"total: {total}")


def _confirm_repair(orphan_ids: dict[str, list[str]]) -> bool:
    total = sum(len(ids) for ids in orphan_ids.values())
    answer = input(f"Delete {total} orphan rows? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _audit_repair(
    audit_logger: AuditLogger,
    relation: OrphanRelation,
    orphan_id: str,
) -> None:
    audit_logger.for_system("integrity-repair").record(
        event=AuditEvent.INTEGRITY_REPAIR,
        outcome="success",
        resource_type="integrity",
        resource_id=orphan_id,
        parent_resource_id="-",
        http_status=200,
        payload={
            "orphan_table": relation.table,
            "orphan_id": orphan_id,
            "parent_table": relation.parent_table,
            "parent_column": relation.parent_column,
        },
    )


def repair_orphans(
    db_path: str | Path,
    *,
    confirm: bool = False,
    audit_logger: AuditLogger | None = None,
    orphan_ids: dict[str, list[str]] | None = None,
) -> dict[str, int]:
    path = Path(db_path)
    current_orphans = orphan_ids if orphan_ids is not None else scan_orphans(path)
    if not confirm and not _confirm_repair(current_orphans):
        return {table: 0 for table in current_orphans}

    logger = audit_logger or AuditLogger(db_path=path)
    deleted: dict[str, int] = {}
    conn = _open_connection(path)
    try:
        for relation in ORPHAN_RELATIONS:
            table_orphans = current_orphans.get(relation.table, [])
            deleted[relation.table] = 0
            for orphan_id in table_orphans:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    cursor = conn.execute(
                        f"""
                        DELETE FROM {relation.table}
                        WHERE {relation.id_column} = ?
                        """,
                        (orphan_id,),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                if cursor.rowcount > 0:
                    deleted[relation.table] += cursor.rowcount
                    _audit_repair(logger, relation, orphan_id)
    finally:
        conn.close()
    return deleted


def _has_orphans(orphan_ids: dict[str, Iterable[str]]) -> bool:
    return any(orphan_ids.get(relation.table) for relation in ORPHAN_RELATIONS)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    orphan_ids = scan_orphans(args.db)
    _print_counts(orphan_ids)

    if args.check:
        return 1 if _has_orphans(orphan_ids) else 0

    if args.repair:
        deleted = repair_orphans(
            args.db,
            confirm=args.confirm,
            orphan_ids=orphan_ids,
        )
        print("deleted:")
        for table in sorted(deleted):
            print(f"{table}: {deleted[table]}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
