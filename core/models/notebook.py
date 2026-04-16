from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Notebook:
    id: str
    name: str
    created_at: str
    updated_at: str
    source_count: int = 0
    owner_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Notebook":
        return cls(
            id=data["id"],
            name=data["name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            source_count=int(data.get("source_count", 0)),
            owner_id=data.get("owner_id"),
        )

    def to_dict(self) -> dict:
        return asdict(self)
