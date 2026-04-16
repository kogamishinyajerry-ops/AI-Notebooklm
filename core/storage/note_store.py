from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from core.ingestion.transaction import DEFAULT_SPACES_DIR, resolve_space_path, utc_now_iso
from core.models.note import Note
from core.storage.json_store import read_json, write_json_atomic


class NoteStore:
    """
    JSON-persisted store for user-saved notes, scoped per notebook.
    Storage: data/spaces/{notebook_id}/notes.json
    """

    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR):
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return resolve_space_path(notebook_id, "notes.json", base_dir=self.spaces_dir)

    def _read(self, notebook_id: str) -> List[Note]:
        data = read_json(self._path(notebook_id), default=[])
        return [Note.from_dict(item) for item in data]

    def _write(self, notebook_id: str, notes: List[Note]) -> None:
        write_json_atomic(self._path(notebook_id), [n.to_dict() for n in notes])

    def create(
        self,
        notebook_id: str,
        content: str,
        citations: List[dict],
        title: str | None = None,
    ) -> Note:
        now = utc_now_iso()
        note = Note(
            id=str(uuid.uuid4()),
            notebook_id=notebook_id,
            title=title or Note.default_title(content),
            content=content,
            citations=citations,
            created_at=now,
            updated_at=now,
        )
        notes = self._read(notebook_id)
        notes.append(note)
        self._write(notebook_id, notes)
        return note

    def list_by_notebook(self, notebook_id: str) -> List[Note]:
        return self._read(notebook_id)

    def get(self, notebook_id: str, note_id: str) -> Note | None:
        return next((n for n in self._read(notebook_id) if n.id == note_id), None)

    def update(
        self,
        notebook_id: str,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> Note:
        notes = self._read(notebook_id)
        for idx, note in enumerate(notes):
            if note.id != note_id:
                continue
            if title is not None:
                note.title = title
            if content is not None:
                note.content = content
            note.updated_at = utc_now_iso()
            notes[idx] = note
            self._write(notebook_id, notes)
            return note
        raise KeyError(note_id)

    def delete(self, notebook_id: str, note_id: str) -> bool:
        notes = self._read(notebook_id)
        remaining = [n for n in notes if n.id != note_id]
        if len(remaining) == len(notes):
            return False
        self._write(notebook_id, remaining)
        return True
