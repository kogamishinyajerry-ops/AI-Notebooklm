"""
core/storage/notebook_store.py
==============================
V4.1-T2: SQLite-backed NotebookStore.

Migrated from JSON (data/notebooks.json) to SQLite (data/notebooks.db).
Foreign-key CASCADE handles deletion of all per-notebook records atomically.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.notebook import Notebook
from core.storage.json_store import read_json, write_json_atomic


def _run_migration(base_dir, db_path, spaces_dir):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import run_migration_if_needed
    return run_migration_if_needed(base_dir=base_dir, db_path=db_path, spaces_dir=spaces_dir)


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class NotebookStore:
    """
    SQLite-persisted store for notebooks.
    Storage: data/notebooks.db (notebooks table)

    On first instantiation, runs JSON→SQLite migration if needed.
    """

    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        spaces_dir: str | Path = DEFAULT_SPACES_DIR,
        *,
        _auto_migrate: bool = True,
    ):
        self.db_path = Path(db_path)
        self.spaces_dir = Path(spaces_dir)

        if _auto_migrate:
            _run_migration(
                base_dir=self.db_path.parent,
                db_path=self.db_path,
                spaces_dir=self.spaces_dir,
            )

    def _conn(self):
        """Return a new connection (caller must close)."""
        return _get_conn(self.db_path)

    def create(self, name: str, owner_id: str | None = None) -> Notebook:
        now = utc_now_iso()
        notebook = Notebook(
            id=str(uuid.uuid4()),
            name=name.strip(),
            created_at=now,
            updated_at=now,
            source_count=0,
            owner_id=owner_id,
        )
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO notebooks
                   (id, name, created_at, updated_at, source_count, owner_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    notebook.id, notebook.name, notebook.created_at,
                    notebook.updated_at, notebook.source_count, notebook.owner_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        (self.spaces_dir / notebook.id).mkdir(parents=True, exist_ok=True)
        return notebook

    def get(self, notebook_id: str) -> Notebook | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM notebooks WHERE id = ?", (notebook_id,)
            ).fetchone()
            if not row:
                return None
            return Notebook(
                id=row["id"], name=row["name"],
                created_at=row["created_at"], updated_at=row["updated_at"],
                source_count=row["source_count"], owner_id=row["owner_id"],
            )
        finally:
            conn.close()

    def list_all(self) -> list[Notebook]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM notebooks ORDER BY created_at ASC"
            ).fetchall()
            return [
                Notebook(
                    id=r["id"], name=r["name"],
                    created_at=r["created_at"], updated_at=r["updated_at"],
                    source_count=r["source_count"], owner_id=r["owner_id"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def update(self, notebook_id: str, **fields) -> Notebook:
        now = utc_now_iso()
        allowed = {"name", "owner_id", "source_count"}
        setters, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown notebook field: {key}")
            setters.append(f"{key} = ?")
            values.append(value)
        if not setters:
            raise ValueError("No fields to update")
        setters.append("updated_at = ?")
        values.append(now)
        values.append(notebook_id)

        conn = self._conn()
        try:
            cur = conn.execute(
                f"UPDATE notebooks SET {', '.join(setters)} WHERE id = ?",
                values,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(notebook_id)
            return self.get(notebook_id)
        finally:
            conn.close()

    def increment_source_count(self, notebook_id: str, delta: int) -> Notebook:
        now = utc_now_iso()
        conn = self._conn()
        try:
            cur = conn.execute(
                """UPDATE notebooks
                   SET source_count = MAX(0, source_count + ?), updated_at = ?
                   WHERE id = ?""",
                (delta, now, notebook_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(notebook_id)
            return self.get(notebook_id)
        finally:
            conn.close()

    def delete(self, notebook_id: str) -> bool:
        conn = self._conn()
        try:
            # ON DELETE CASCADE in SQLite FK removes all child records atomically
            cur = conn.execute(
                "DELETE FROM notebooks WHERE id = ?", (notebook_id,)
            )
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()

        if deleted:
            shutil.rmtree(self.spaces_dir / notebook_id, ignore_errors=True)
        return deleted
