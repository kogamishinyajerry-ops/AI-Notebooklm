from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import List


class StudioOutputType(str, Enum):
    SUMMARY      = "summary"
    FAQ          = "faq"
    BRIEFING     = "briefing"
    GLOSSARY     = "glossary"
    ACTION_ITEMS = "action_items"
    PODCAST      = "podcast"
    INFOGRAPHIC  = "infographic"

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def labels(cls) -> dict:
        return {
            cls.SUMMARY:      "执行摘要",
            cls.FAQ:          "FAQ 问答",
            cls.BRIEFING:     "技术简报",
            cls.GLOSSARY:     "术语表",
            cls.ACTION_ITEMS: "行动项",
            cls.PODCAST:      "播客导览",
            cls.INFOGRAPHIC:  "信息图",
        }


@dataclass
class StudioOutput:
    """A generated structured text output, scoped to a notebook."""

    id: str
    notebook_id: str
    output_type: str           # StudioOutputType.value
    title: str                 # human-readable label (type label + timestamp suffix)
    content: str               # generated text
    citations: List[dict]      # [{source_file, page_number, content, bbox}]
    created_at: str            # ISO 8601 UTC

    @classmethod
    def from_dict(cls, data: dict) -> "StudioOutput":
        return cls(
            id=data["id"],
            notebook_id=data["notebook_id"],
            output_type=data["output_type"],
            title=data.get("title", data["output_type"]),
            content=data["content"],
            citations=data.get("citations", []),
            created_at=data["created_at"],
        )

    def to_dict(self) -> dict:
        return asdict(self)
