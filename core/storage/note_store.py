"""
core/storage/note_store.py
==========================
V4.1-T2: SQLite-backed NoteStore.

Per-notebook notes persisted in data/notebooks.db (notes table).
No per-notebook JSON files.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.note import Note


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class NoteStore:
    """
    SQLite-persisted store for user-saved notes, scoped per notebook.
    Storage: data/notebooks.db (notes table)
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
        # Disable FK enforcement for this store — notes can be created for
        # notebooks that don't yet exist in the DB (backward compatible with
        # the original JSON-per-notebook design). ON DELETE CASCADE on
        # NotebookStore.delete() still cascades child records atomically when
        # the parent notebook is deleted from notebooks table.
        conn.execute("PRAGMA foreign_keys=OFF")
        return conn

    def create(
        self,
        notebook_id: str,
        content: str,
        citations: List[dict],
        title: str | None = None,
    ) -> Note:
        now = utc_now_iso()
        note = Note(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            title=title or Note.default_title(content),
            content=content,
            citations=citations,
            created_at=now,
            updated_at=now,
        )
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO notes
                   (id, notebook_id, title, content, citations, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    note.id, note.notebook_id, note.title, note.content,
                    json.dumps(note.citations, ensure_ascii=False),
                    note.created_at, note.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return note

    def list_by_notebook(self, notebook_id: str) -> List[Note]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM notes WHERE notebook_id = ? ORDER BY created_at ASC",
                (notebook_id,),
            ).fetchall()
            return [self._row_to_note(r) for r in rows]
        finally:
            conn.close()

    def get(self, notebook_id: str, note_id: str) -> Note | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ? AND notebook_id = ?",
                (note_id, notebook_id),
            ).fetchone()
            return self._row_to_note(row) if row else None
        finally:
            conn.close()

    def update(
        self,
        notebook_id: str,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> Note:
        now = utc_now_iso()
        setters, values = [], []
        if title is not None:
            setters.append("title = ?")
            values.append(title)
        if content is not None:
            setters.append("content = ?")
            values.append(content)
        if not setters:
            raise ValueError("No fields to update")
        setters.append("updated_at = ?")
        values.append(now)
        values.extend([note_id, notebook_id])

        conn = self._conn()
        try:
            cur = conn.execute(
                f"""UPDATE notes SET {', '.join(setters)}
                    WHERE id = ? AND notebook_id = ?""",
                values,
            )
            conn.commit()
            if cur.rowcount == 0:
                raise KeyError(note_id)
            return self.get(notebook_id, note_id)
        finally:
            conn.close()

    def delete(self, notebook_id: str, note_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM notes WHERE id = ? AND notebook_id = ?",
                (note_id, notebook_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def _row_to_note(self, row) -> Note:
        return Note(
            id=row["id"],
            notebook_id=row["notebook_id"],
            title=row["title"],
            content=row["content"],
            citations=json.loads(row["citations"]) if row["citations"] else [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
