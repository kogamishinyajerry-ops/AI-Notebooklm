"""V4.2-T4: Legacy Notebook Ownership Migration CLI.

Closes Opus V3.3 F-4: notebooks rows created before V3.3-P4 (which
introduced per-principal ownership) may carry ``owner_id IS NULL`` or
``owner_id = ''``. This CLI assigns an owner to those rows idempotently,
with dry-run, principal validation, and per-row audit emission.

Usage
-----
Read-only inventory (safe on any DB, no writes, exit 0):
    python scripts/migrate_notebook_ownership.py --db PATH --report-only

Dry-run plan (no writes, exit 1 iff work is pending):
    python scripts/migrate_notebook_ownership.py --db PATH --owner alice --dry-run

Real migration (transactional + audit, exit 0 on success):
    python scripts/migrate_notebook_ownership.py --db PATH --owner alice --assume-yes

Contract: FD-1..FD-10 in docs/v4_2_t4_freeze_pack.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

# Allow running as a standalone script (``python scripts/migrate_*.py``) by
# making the repo root importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.storage.sqlite_db import get_connection  # noqa: E402


EXIT_OK = 0
EXIT_DRY_RUN_PENDING = 1
EXIT_VALIDATION_FAILED = 2
EXIT_IO_ERROR = 3


def _load_allowed_principals() -> set[str]:
    """Extract principal_ids from NOTEBOOKLM_API_KEYS (FD-4)."""
    from core.security.auth import get_api_key_registry

    registry = get_api_key_registry()
    return {p.principal_id for p in registry.values()}


def _fetch_legacy_rows(conn, notebook_ids: Sequence[str] | None = None) -> list[dict]:
    """Return rows where owner_id IS NULL OR owner_id = '' (FD-2)."""
    sql = (
        "SELECT id, name, created_at, owner_id "
        "FROM notebooks "
        "WHERE (owner_id IS NULL OR owner_id = '')"
    )
    params: list = []
    if notebook_ids:
        placeholders = ",".join("?" for _ in notebook_ids)
        sql += f" AND id IN ({placeholders})"
        params.extend(notebook_ids)
    sql += " ORDER BY created_at ASC, id ASC"
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _fetch_all_rows(conn, notebook_ids: Sequence[str] | None = None) -> list[dict]:
    """Return all rows (for --force: legacy + non-legacy both candidates)."""
    sql = "SELECT id, name, created_at, owner_id FROM notebooks"
    params: list = []
    if notebook_ids:
        placeholders = ",".join("?" for _ in notebook_ids)
        sql += f" WHERE id IN ({placeholders})"
        params.extend(notebook_ids)
    sql += " ORDER BY created_at ASC, id ASC"
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _year_of(iso_ts: str) -> str:
    return iso_ts[:4] if iso_ts else "-"


def _print_report(rows: list[dict], out) -> None:
    """Read-only summary (FD-6). Exit always 0."""
    if not rows:
        print("no legacy notebook rows (owner_id IS NULL OR '') — nothing to report", file=out)
        return
    by_year = Counter(_year_of(r["created_at"]) for r in rows)
    print(f"legacy notebook rows: {len(rows)}", file=out)
    print("grouped by created_at year:", file=out)
    for year, count in sorted(by_year.items()):
        print(f"  {year}: {count}", file=out)
    print("sample ids (first 10):", file=out)
    for row in rows[:10]:
        print(f"  - {row['id']}  name={row['name']!r}  created_at={row['created_at']}", file=out)


def _print_dry_run(rows: list[dict], target_owner: str, forced: bool, out) -> None:
    """Plan emission (FD-5). No writes, no audit."""
    if not rows:
        print("no rows require migration — dry-run clean", file=out)
        return
    verb = "OVERWRITE" if forced else "ASSIGN"
    print(f"dry-run: would {verb} owner_id → {target_owner!r} for {len(rows)} notebook(s):", file=out)
    for row in rows:
        cur = row["owner_id"] if row["owner_id"] not in (None, "") else "<null>"
        print(f"  {row['id']}  from={cur!r}  to={target_owner!r}  created_at={row['created_at']}", file=out)


def _apply_migration(conn, rows: list[dict], target_owner: str, forced: bool, audit_logger) -> int:
    """Transactional write (FD-7) + audit emission (FD-8).

    Returns count of rows migrated. Rolls back and raises on any failure.
    """
    if not rows:
        return 0

    try:
        conn.execute("BEGIN IMMEDIATE")
        migrated = 0
        for row in rows:
            result = conn.execute(
                "UPDATE notebooks SET owner_id = ? WHERE id = ?",
                (target_owner, row["id"]),
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    f"expected 1 row updated for notebook {row['id']!r}, got {result.rowcount}"
                )
            migrated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Audit emission is AFTER commit so audit rows only describe persisted
    # state. If audit append fails, the AuditLogger falls back to JSON log
    # (see audit_logger._append_with_fallback) — we don't roll back the
    # migration for an audit-transport failure.
    if audit_logger is not None:
        system_logger = audit_logger.for_system("migrate_notebook_ownership")
        for row in rows:
            from_owner = row["owner_id"] if row["owner_id"] not in (None, "") else ""
            system_logger.record(
                event="notebook.migrate_owner",
                outcome="success",
                resource_type="notebook",
                resource_id=row["id"],
                http_status=200,
                payload={
                    "migrate.from_owner": from_owner,
                    "migrate.to_owner": target_owner,
                    "migrate.forced": bool(forced),
                },
            )

    return migrated


def _confirm(target_owner: str, count: int, forced: bool, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    verb = "OVERWRITE" if forced else "assign"
    prompt = f"About to {verb} owner_id={target_owner!r} for {count} notebook(s). Proceed? [y/N] "
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migrate_notebook_ownership",
        description="Assign owner_id to legacy notebook rows (V4.2-T4 / Opus V3.3 F-4).",
    )
    p.add_argument("--db", required=True, help="Path to notebooks.db")
    p.add_argument("--owner", help="Target principal_id (must exist in NOTEBOOKLM_API_KEYS)")
    p.add_argument("--dry-run", action="store_true", help="Plan only — no writes, no audit")
    p.add_argument("--report-only", action="store_true", help="Inventory summary — always exit 0")
    p.add_argument("--force", action="store_true", help="Also rewrite non-legacy owner_id values")
    p.add_argument(
        "--notebook-id",
        action="append",
        default=[],
        help="Limit to this notebook id (repeatable)",
    )
    p.add_argument("--assume-yes", action="store_true", help="Skip interactive confirmation")
    return p


def main(argv: Sequence[str] | None = None, *, audit_logger=None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return EXIT_IO_ERROR

    try:
        conn = get_connection(db_path)
    except Exception as exc:  # pragma: no cover — defensive
        print(f"error: cannot open db: {exc}", file=sys.stderr)
        return EXIT_IO_ERROR

    try:
        notebook_filter = args.notebook_id or None

        if args.report_only:
            rows = _fetch_legacy_rows(conn, notebook_filter)
            _print_report(rows, out)
            return EXIT_OK

        # All non-report modes require --owner.
        if not args.owner:
            print("error: --owner is required unless --report-only is set", file=sys.stderr)
            return EXIT_VALIDATION_FAILED

        # FD-4: principal must exist in NOTEBOOKLM_API_KEYS.
        allowed = _load_allowed_principals()
        if not allowed:
            print(
                "error: NOTEBOOKLM_API_KEYS is not configured; cannot validate --owner",
                file=sys.stderr,
            )
            return EXIT_VALIDATION_FAILED
        if args.owner not in allowed:
            print(
                f"error: --owner {args.owner!r} not in NOTEBOOKLM_API_KEYS allowlist",
                file=sys.stderr,
            )
            return EXIT_VALIDATION_FAILED

        rows = (
            _fetch_all_rows(conn, notebook_filter)
            if args.force
            else _fetch_legacy_rows(conn, notebook_filter)
        )
        # Under --force we still skip rows that already equal target_owner
        # (FD-3 idempotency: re-running with same owner is a no-op).
        rows = [r for r in rows if (r["owner_id"] or "") != args.owner]

        if args.dry_run:
            _print_dry_run(rows, args.owner, args.force, out)
            return EXIT_DRY_RUN_PENDING if rows else EXIT_OK

        if not rows:
            print(f"no rows require migration for owner={args.owner!r} — nothing to do", file=out)
            return EXIT_OK

        if not _confirm(args.owner, len(rows), args.force, args.assume_yes):
            print("aborted by operator", file=out)
            return EXIT_OK

        try:
            migrated = _apply_migration(conn, rows, args.owner, args.force, audit_logger)
        except Exception as exc:
            print(f"error: migration failed, rolled back: {exc}", file=sys.stderr)
            return EXIT_IO_ERROR

        print(f"migrated {migrated} notebook(s) → owner_id={args.owner!r}", file=out)
        return EXIT_OK
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
