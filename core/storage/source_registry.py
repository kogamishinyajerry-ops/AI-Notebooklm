from __future__ import annotations

import uuid
from pathlib import Path

from core.ingestion.transaction import DEFAULT_SPACES_DIR, resolve_space_path, utc_now_iso
from core.models.source import Source, SourceStatus
from core.storage.json_store import read_json, write_json_atomic


class SourceRegistry:
    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR):
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return resolve_space_path(notebook_id, "sources.json", base_dir=self.spaces_dir)

    def _read(self, notebook_id: str) -> list[Source]:
        data = read_json(self._path(notebook_id), default=[])
        return [Source.from_dict(item) for item in data]

    def _write(self, notebook_id: str, sources: list[Source]) -> None:
        write_json_atomic(self._path(notebook_id), [source.to_dict() for source in sources])

    def register(self, notebook_id: str, filename: str, file_path: str) -> Source:
        now = utc_now_iso()
        source = Source(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            filename=filename,
            file_path=file_path,
            page_count=None,
            chunk_count=None,
            status=SourceStatus.UPLOADING,
            created_at=now,
            updated_at=now,
        )
        sources = self._read(notebook_id)
        sources.append(source)
        self._write(notebook_id, sources)
        return source

    def get(self, notebook_id: str, source_id: str) -> Source | None:
        return next((source for source in self._read(notebook_id) if source.id == source_id), None)

    def list_by_notebook(self, notebook_id: str) -> list[Source]:
        return self._read(notebook_id)

    def update_status(
        self,
        notebook_id: str,
        source_id: str,
        status: SourceStatus | str,
        page_count: int | None = None,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> Source:
        next_status = status if isinstance(status, SourceStatus) else SourceStatus(status)
        sources = self._read(notebook_id)
        for index, source in enumerate(sources):
            if source.id != source_id:
                continue

            source.status = next_status
            source.updated_at = utc_now_iso()
            if page_count is not None:
                source.page_count = page_count
            if chunk_count is not None:
                source.chunk_count = chunk_count
            source.error_message = error_message
            sources[index] = source
            self._write(notebook_id, sources)
            return source
        raise KeyError(source_id)

    def delete(self, notebook_id: str, source_id: str) -> bool:
        sources = self._read(notebook_id)
        remaining = [source for source in sources if source.id != source_id]
        if len(remaining) == len(sources):
            return False
        self._write(notebook_id, remaining)
        return True
