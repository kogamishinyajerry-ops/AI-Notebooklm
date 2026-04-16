from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

from core.ingestion.transaction import DEFAULT_SPACES_DIR, resolve_space_path, utc_now_iso
from core.models.studio_output import StudioOutput
from core.storage.json_store import read_json, write_json_atomic


class StudioStore:
    """
    JSON-persisted store for Text Studio generated outputs, scoped per notebook.
    Storage: data/spaces/{notebook_id}/studio.json
    """

    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR):
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return resolve_space_path(notebook_id, "studio.json", base_dir=self.spaces_dir)

    def _read(self, notebook_id: str) -> List[StudioOutput]:
        data = read_json(self._path(notebook_id), default=[])
        return [StudioOutput.from_dict(item) for item in data]

    def _write(self, notebook_id: str, outputs: List[StudioOutput]) -> None:
        write_json_atomic(self._path(notebook_id), [o.to_dict() for o in outputs])

    def create(
        self,
        notebook_id: str,
        output_type: str,
        content: str,
        citations: List[dict],
        title: str | None = None,
    ) -> StudioOutput:
        now = utc_now_iso()
        # Auto-title: type label + timestamp suffix (last 5 chars of ISO string)
        from core.models.studio_output import StudioOutputType
        type_labels = StudioOutputType.labels()
        try:
            label = type_labels[StudioOutputType(output_type)]
        except (KeyError, ValueError):
            label = output_type
        auto_title = title or f"{label} · {now[11:16]}"

        output = StudioOutput(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            output_type=output_type,
            title=auto_title,
            content=content,
            citations=citations,
            created_at=now,
        )
        outputs = self._read(notebook_id)
        outputs.append(output)
        self._write(notebook_id, outputs)
        return output

    def list_by_notebook(self, notebook_id: str) -> List[StudioOutput]:
        return self._read(notebook_id)

    def get(self, notebook_id: str, output_id: str) -> Optional[StudioOutput]:
        return next((o for o in self._read(notebook_id) if o.id == output_id), None)

    def delete(self, notebook_id: str, output_id: str) -> bool:
        outputs = self._read(notebook_id)
        remaining = [o for o in outputs if o.id != output_id]
        if len(remaining) == len(outputs):
            return False
        self._write(notebook_id, remaining)
        return True
