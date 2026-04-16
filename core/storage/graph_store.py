"""
core/storage/graph_store.py
============================
S-23: Persistent store for KnowledgeGraph objects.

Storage path: data/spaces/{notebook_id}/graph.json
Uses write_json_atomic for crash-safe writes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.storage.json_store import read_json, write_json_atomic
from core.models.graph import KnowledgeGraph

DEFAULT_SPACES_DIR = Path("data/spaces")


class GraphStore:
    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR) -> None:
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return self.spaces_dir / notebook_id / "graph.json"

    def save(self, notebook_id: str, graph: KnowledgeGraph) -> None:
        """Persist the graph; overwrites any previously saved graph."""
        path = self._path(notebook_id)
        write_json_atomic(path, graph.to_dict())

    def load(self, notebook_id: str) -> Optional[KnowledgeGraph]:
        """Load the graph for *notebook_id*, or None if not yet generated."""
        path = self._path(notebook_id)
        data = read_json(path, default=None)
        if data is None:
            return None
        return KnowledgeGraph.from_dict(data)

    def exists(self, notebook_id: str) -> bool:
        return self._path(notebook_id).exists()

    def delete(self, notebook_id: str) -> bool:
        path = self._path(notebook_id)
        if path.exists():
            path.unlink()
            return True
        return False
