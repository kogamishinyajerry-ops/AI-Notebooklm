"""
core/storage/graph_store.py
============================
S-23 + Gap-A: Persistent store for KnowledgeGraph objects.

Changes vs S-23 baseline:
  * get_neighbors(entity, depth) — BFS over the adjacency list built from
    GraphEdge data; returns entity labels reachable within *depth* hops.
  * get_source_chunks(entity) — returns the chunk_ids reverse-indexed from
    GraphNode.chunk_ids; used by RetrieverEngine._graph_expand().

Both methods are C1 compliant (no external calls, pure Python dict BFS).

Storage path: data/spaces/{notebook_id}/graph.json
Uses write_json_atomic for crash-safe writes.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.storage.json_store import read_json, write_json_atomic
from core.models.graph import KnowledgeGraph

DEFAULT_SPACES_DIR = Path("data/spaces")


class GraphStore:
    def __init__(self, spaces_dir: str | Path = DEFAULT_SPACES_DIR) -> None:
        self.spaces_dir = Path(spaces_dir)

    def _path(self, notebook_id: str) -> Path:
        return self.spaces_dir / notebook_id / "graph.json"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Gap-A retrieval helpers
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        notebook_id: str,
        entity_label: str,
        depth: int = 1,
    ) -> List[str]:
        """
        BFS over the knowledge graph and return entity *labels* reachable
        from *entity_label* within *depth* hops.

        Returns an empty list when:
        - no graph exists for the notebook
        - *entity_label* is not present as a node label

        C1 compliant — pure dict BFS, no external calls.

        Parameters
        ----------
        notebook_id:
            Identifies which notebook's graph to traverse.
        entity_label:
            The human-readable label of the starting entity (e.g. "CFD").
        depth:
            Maximum BFS depth (1 = direct neighbours only).
        """
        graph = self.load(notebook_id)
        if graph is None or not graph.nodes:
            return []

        # Build label→node_id mapping and adjacency list (by id)
        label_to_id: Dict[str, str] = {n.label: n.id for n in graph.nodes}
        id_to_label: Dict[str, str] = {n.id: n.label for n in graph.nodes}

        start_id = label_to_id.get(entity_label)
        if start_id is None:
            return []

        # Build undirected adjacency list from edges
        adjacency: Dict[str, List[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adjacency and edge.target in adjacency:
                adjacency[edge.source].append(edge.target)
                adjacency[edge.target].append(edge.source)

        # BFS
        visited: Set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        result: List[str] = []

        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbour_id in adjacency.get(node_id, []):
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    result.append(id_to_label[neighbour_id])
                    queue.append((neighbour_id, current_depth + 1))

        return result

    def get_source_chunks(
        self,
        notebook_id: str,
        entity_label: str,
    ) -> List[str]:
        """
        Return the chunk_ids associated with *entity_label* in the stored
        knowledge graph's reverse-index (GraphNode.chunk_ids).

        Returns an empty list when:
        - no graph exists for the notebook
        - *entity_label* is not found in the graph nodes

        C1 compliant — pure Python, no external calls.
        """
        graph = self.load(notebook_id)
        if graph is None:
            return []

        for node in graph.nodes:
            if node.label == entity_label:
                return list(node.chunk_ids)

        return []
