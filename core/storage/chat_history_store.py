from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from core.ingestion.transaction import DEFAULT_SPACES_DIR, resolve_space_path, utc_now_iso
from core.models.chat_message import ChatMessage
from core.storage.json_store import read_json, write_json_atomic

# Maximum messages retained per notebook (FIFO eviction beyond this)
MAX_HISTORY = 200


class ChatHistoryStore:
    """
    JSON-persisted store for per-notebook chat history.
    Storage: data/spaces/{notebook_id}/chat_history.json
    Keeps the most recent MAX_HISTORY messages; older entries are evicted.
    """

    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR):
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return resolve_space_path(notebook_id, "chat_history.json", base_dir=self.spaces_dir)

    def _read(self, notebook_id: str) -> List[ChatMessage]:
        data = read_json(self._path(notebook_id), default=[])
        return [ChatMessage.from_dict(item) for item in data]

    def _write(self, notebook_id: str, messages: List[ChatMessage]) -> None:
        write_json_atomic(self._path(notebook_id), [m.to_dict() for m in messages])

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
        messages = self._read(notebook_id)
        messages.append(message)
        # FIFO eviction — retain only the most recent MAX_HISTORY entries
        if len(messages) > MAX_HISTORY:
            messages = messages[-MAX_HISTORY:]
        self._write(notebook_id, messages)
        return message

    def list_by_notebook(self, notebook_id: str, limit: int = 100) -> List[ChatMessage]:
        messages = self._read(notebook_id)
        return messages[-limit:] if limit > 0 else messages

    def clear(self, notebook_id: str) -> int:
        messages = self._read(notebook_id)
        count = len(messages)
        self._write(notebook_id, [])
        return count
