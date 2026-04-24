from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeneratedMedia:
    data: bytes
    media_type: str
    file_extension: str
    trace_id: str | None = None
    extra_info: dict[str, Any] | None = None
