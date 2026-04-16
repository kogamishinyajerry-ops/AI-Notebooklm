from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List


@dataclass
class ChatMessage:
    """A single turn in a notebook's chat history."""

    id: str
    notebook_id: str
    role: str               # "user" | "assistant"
    content: str
    citations: List[dict]   # populated for assistant messages
    is_fully_verified: bool
    created_at: str         # ISO 8601 UTC

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            id=data["id"],
            notebook_id=data["notebook_id"],
            role=data["role"],
            content=data["content"],
            citations=data.get("citations", []),
            is_fully_verified=data.get("is_fully_verified", False),
            created_at=data["created_at"],
        )

    def to_dict(self) -> dict:
        return asdict(self)
