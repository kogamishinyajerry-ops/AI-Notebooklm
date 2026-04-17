from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class SourceStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class Source:
    id: str
    notebook_id: str
    filename: str
    file_path: str
    page_count: int | None
    chunk_count: int | None
    status: SourceStatus
    created_at: str
    updated_at: str
    error_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Source":
        return cls(
            id=data["id"],
            notebook_id=data["notebook_id"],
            filename=data["filename"],
            file_path=data["file_path"],
            page_count=data.get("page_count"),
            chunk_count=data.get("chunk_count"),
            status=SourceStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            error_message=data.get("error_message"),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data
