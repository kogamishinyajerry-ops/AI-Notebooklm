from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.notebook import Notebook
from core.storage.json_store import read_json, write_json_atomic


DEFAULT_NOTEBOOKS_PATH = Path("data/notebooks.json")


class NotebookStore:
    def __init__(
        self,
        notebooks_path: str | Path = DEFAULT_NOTEBOOKS_PATH,
        spaces_dir: str | Path = DEFAULT_SPACES_DIR,
    ):
        self.notebooks_path = Path(notebooks_path)
        self.spaces_dir = Path(spaces_dir)

    def _read(self) -> list[Notebook]:
        data = read_json(self.notebooks_path, default=[])
        return [Notebook.from_dict(item) for item in data]

    def _write(self, notebooks: list[Notebook]) -> None:
        write_json_atomic(self.notebooks_path, [notebook.to_dict() for notebook in notebooks])

    def create(self, name: str) -> Notebook:
        trimmed_name = name.strip()
        if not trimmed_name:
            raise ValueError("Notebook name is required")

        now = utc_now_iso()
        notebook = Notebook(
            id=str(uuid.uuid4()),
            name=trimmed_name,
            created_at=now,
            updated_at=now,
            source_count=0,
        )
        notebooks = self._read()
        notebooks.append(notebook)
        self._write(notebooks)
        (self.spaces_dir / notebook.id).mkdir(parents=True, exist_ok=True)
        return notebook

    def get(self, notebook_id: str) -> Notebook | None:
        return next((notebook for notebook in self._read() if notebook.id == notebook_id), None)

    def list_all(self) -> list[Notebook]:
        return self._read()

    def update(self, notebook_id: str, **fields) -> Notebook:
        notebooks = self._read()
        for index, notebook in enumerate(notebooks):
            if notebook.id != notebook_id:
                continue

            for key, value in fields.items():
                if not hasattr(notebook, key):
                    raise ValueError(f"Unknown notebook field: {key}")
                setattr(notebook, key, value)
            notebook.updated_at = utc_now_iso()
            notebooks[index] = notebook
            self._write(notebooks)
            return notebook
        raise KeyError(notebook_id)

    def increment_source_count(self, notebook_id: str, delta: int) -> Notebook:
        notebook = self.get(notebook_id)
        if notebook is None:
            raise KeyError(notebook_id)
        next_count = max(0, notebook.source_count + delta)
        return self.update(notebook_id, source_count=next_count)

    def delete(self, notebook_id: str) -> bool:
        notebooks = self._read()
        remaining = [notebook for notebook in notebooks if notebook.id != notebook_id]
        if len(remaining) == len(notebooks):
            return False
        self._write(remaining)
        shutil.rmtree(self.spaces_dir / notebook_id, ignore_errors=True)
        return True
