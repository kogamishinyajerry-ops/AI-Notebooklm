"""
core/storage/source_registry.py
===============================
V4.1-T2: SQLite-backed SourceRegistry.

Per-notebook sources persisted in data/notebooks.db (sources table).
No per-notebook JSON files.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.source import Source, SourceStatus


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class SourceRegistry:
    """
    SQLite-persisted registry of uploaded sources per notebook.
    Storage: data/notebooks.db (sources table)
    """

    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        spaces_dir: str | Path = DEFAULT_SPACES_DIR,
    ):
        self.db_path = Path(db_path)
        self.spaces_dir = Path(spaces_dir)

    def _conn(self):
        conn = _get_conn(self.db_path)
        conn.execute("PRAGMA foreign_keys=OFF")
        return conn

    def register(
        self, notebook_id: str, filename: str, file_path: str
    ) -> Source:
        now = utc_now_iso()
        source = Source(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            filename=filename,
            file_path=file_path,
            page_count=None,
            chunk_count=None,
            status=SourceStatus.UPLOADING,
            created_at=now,
            updated_at=now,
        )
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO sources
                   (id, notebook_id, filename, file_path, status,
                    page_count, chunk_count, created_at, updated_at, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.id, source.notebook_id, source.filename,
                    source.file_path, source.status.value,
                    source.page_count, source.chunk_count,
                    source.created_at, source.updated_at, source.error_message,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return source

    def get(self, notebook_id: str, source_id: str) -> Source | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM sources WHERE id = ? AND notebook_id = ?",
                (source_id, notebook_id),
            ).fetchone()
            return self._row_to_source(row) if row else None
        finally:
            conn.close()

    def list_by_notebook(self, notebook_id: str) -> list[Source]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM sources WHERE notebook_id = ? ORDER BY created_at ASC",
                (notebook_id,),
            ).fetchall()
            return [self._row_to_source(r) for r in rows]
        finally:
            conn.close()

    def update_status(
        self,
        notebook_id: str,
        source_id: str,
        status: SourceStatus | str,
        page_count: int | None = None,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> Source:
        next_status = (
            status if isinstance(status, SourceStatus) else SourceStatus(status)
        )
        now = utc_now_iso()
        setters, values = ["status = ?", "updated_at = ?"], [next_status.value, now]

        if page_count is not None:
            setters.append("page_count = ?")
            values.append(page_count)
        if chunk_count is not None:
            setters.append("chunk_count = ?")
            values.append(chunk_count)
        if error_message is not None:
            setters.append("error_message = ?")
            values.append(error_message)
        values.extend([source_id, notebook_id])

        conn = self._conn()
        try:
            cur = conn.execute(
                f"""UPDATE sources SET {', '.join(setters)}
                    WHERE id = ? AND notebook_id = ?""",
                values,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(source_id)
            return self.get(notebook_id, source_id)
        finally:
            conn.close()

    def delete(self, notebook_id: str, source_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM sources WHERE id = ? AND notebook_id = ?",
                (source_id, notebook_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def _row_to_source(self, row) -> Source:
        return Source(
            id=row["id"],
            notebook_id=row["notebook_id"],
            filename=row["filename"],
            file_path=row["file_path"],
            status=SourceStatus(row["status"]),
            page_count=row["page_count"],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
        )
