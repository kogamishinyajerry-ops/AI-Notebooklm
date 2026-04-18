"""
core/storage/chat_history_store.py
=================================
V4.1-T2: SQLite-backed ChatHistoryStore.

Per-notebook chat messages persisted in data/notebooks.db (chat_messages table).
MAX_HISTORY=200 FIFO eviction enforced via SQL after each append.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import List

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.chat_message import ChatMessage
from core.storage.exceptions import NotebookNotFound


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn

# Maximum messages retained per notebook (FIFO eviction beyond this)
MAX_HISTORY = 200


class ChatHistoryStore:
    """
    SQLite-persisted store for per-notebook chat history.
    Storage: data/notebooks.db (chat_messages table)
    """

    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        spaces_dir: str | Path = DEFAULT_SPACES_DIR,
    ):
        self.db_path = Path(db_path)
        self.spaces_dir = Path(spaces_dir)

    def _conn(self):
        return _get_conn(self.db_path)

    def append(
        self,
        notebook_id: str,
        role: str,
        content: str,
        citations: List[dict] | None = None,
        is_fully_verified: bool = False,
    ) -> ChatMessage:
        message = ChatMessage(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            role=role,
            content=content,
            citations=citations or [],
            is_fully_verified=is_fully_verified,
            created_at=utc_now_iso(),
        )
        conn = self._conn()
        try:
            try:
                conn.execute(
                    """INSERT INTO chat_messages
                       (id, notebook_id, role, content, citations,
                        is_fully_verified, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message.id, message.notebook_id, message.role,
                        message.content,
                        json.dumps(message.citations, ensure_ascii=False),
                        int(message.is_fully_verified),
                        message.created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "FOREIGN KEY constraint failed" in str(exc):
                    raise NotebookNotFound(notebook_id) from exc
                raise

            # FIFO eviction — delete older messages beyond MAX_HISTORY
            conn.execute(
                """DELETE FROM chat_messages
                   WHERE notebook_id = ? AND id NOT IN (
                       SELECT id FROM chat_messages
                       WHERE notebook_id = ?
                       ORDER BY created_at DESC
                       LIMIT ?
                   )""",
                (notebook_id, notebook_id, MAX_HISTORY),
            )
            conn.commit()
        finally:
            conn.close()
        return message

    def list_by_notebook(
        self, notebook_id: str, limit: int = 100
    ) -> List[ChatMessage]:
        conn = self._conn()
        try:
            if limit > 0:
                # Original: messages[-limit:] on ASC list = limit newest, ASC order
                # SQLite: get limit newest via DESC, then reverse to ASC
                rows = conn.execute(
                    """SELECT * FROM chat_messages
                       WHERE notebook_id = ?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (notebook_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = conn.execute(
                    """SELECT * FROM chat_messages
                       WHERE notebook_id = ?
                       ORDER BY created_at ASC""",
                    (notebook_id,),
                ).fetchall()
            return [self._row_to_message(r) for r in rows]
        finally:
            conn.close()

    def clear(self, notebook_id: str) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM chat_messages WHERE notebook_id = ?",
                (notebook_id,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def _row_to_message(self, row) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            notebook_id=row["notebook_id"],
            role=row["role"],
            content=row["content"],
            citations=(
                json.loads(row["citations"])
                if row["citations"] else []
            ),
            is_fully_verified=bool(row["is_fully_verified"]),
            created_at=row["created_at"],
        )
