from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List


@dataclass
class Note:
    """A user-saved AI response with its citations, scoped to a notebook."""

    id: str
    notebook_id: str
    title: str          # user-editable; defaults to first 40 chars of content
    content: str        # AI answer text (post-Gateway)
    citations: List[dict]  # [{source_file, page_number, content, bbox}]
    created_at: str     # ISO 8601 UTC
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            id=data["id"],
            notebook_id=data["notebook_id"],
            title=data.get("title", ""),
            content=data["content"],
            citations=data.get("citations", []),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def default_title(content: str) -> str:
        stripped = content.strip().replace("\n", " ")
        return stripped[:40] + ("…" if len(stripped) > 40 else "")
