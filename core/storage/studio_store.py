"""
core/storage/studio_store.py
=============================
V4.1-T2: SQLite-backed StudioStore.

Per-notebook studio outputs persisted in data/notebooks.db (studio_outputs table).
No per-notebook JSON files.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.studio_output import StudioOutput


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class StudioStore:
    """
    SQLite-persisted store for Text Studio generated outputs, scoped per notebook.
    Storage: data/notebooks.db (studio_outputs table)
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

    def create(
        self,
        notebook_id: str,
        output_type: str,
        content: str,
        citations: List[dict],
        title: str | None = None,
    ) -> StudioOutput:
        now = utc_now_iso()
        from core.models.studio_output import StudioOutputType

        type_labels = StudioOutputType.labels()
        try:
            label = type_labels[StudioOutputType(output_type)]
        except (KeyError, ValueError):
            label = output_type
        auto_title = title or f"{label} · {now[11:16]}"

        output = StudioOutput(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            output_type=output_type,
            title=auto_title,
            content=content,
            citations=citations,
            created_at=now,
        )
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO studio_outputs
                   (id, notebook_id, output_type, title, content, citations, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    output.id, output.notebook_id, output.output_type,
                    output.title, output.content,
                    json.dumps(output.citations, ensure_ascii=False),
                    output.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return output

    def list_by_notebook(self, notebook_id: str) -> List[StudioOutput]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM studio_outputs
                   WHERE notebook_id = ?
                   ORDER BY created_at ASC""",
                (notebook_id,),
            ).fetchall()
            return [self._row_to_output(r) for r in rows]
        finally:
            conn.close()

    def get(self, notebook_id: str, output_id: str) -> Optional[StudioOutput]:
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT * FROM studio_outputs
                   WHERE id = ? AND notebook_id = ?""",
                (output_id, notebook_id),
            ).fetchone()
            return self._row_to_output(row) if row else None
        finally:
            conn.close()

    def delete(self, notebook_id: str, output_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM studio_outputs WHERE id = ? AND notebook_id = ?",
                (output_id, notebook_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def _row_to_output(self, row) -> StudioOutput:
        return StudioOutput(
            id=row["id"],
            notebook_id=row["notebook_id"],
            output_type=row["output_type"],
            title=row["title"],
            content=row["content"],
            citations=(
                json.loads(row["citations"])
                if row["citations"] else []
            ),
            created_at=row["created_at"],
        )
