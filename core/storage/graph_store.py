"""
core/storage/graph_store.py
===========================
V4.1-T2: SQLite-backed GraphStore.

Per-notebook knowledge graphs persisted in data/notebooks.db (knowledge_graphs table).
nodes/edges/mindmap stored as JSON TEXT; in-memory BFS helpers unchanged.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.ingestion.transaction import DEFAULT_SPACES_DIR, utc_now_iso
from core.models.graph import KnowledgeGraph
from core.storage.exceptions import NotebookNotFound


def _get_conn(db_path):
    """Deferred import to avoid breaking test_cross_notebook_isolation."""
    from core.storage.sqlite_db import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    return conn

DEFAULT_SPACES_DIR = Path("data/spaces")


class GraphStore:
    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        spaces_dir: str | Path = DEFAULT_SPACES_DIR,
    ):
        self.db_path = Path(db_path)
        self.spaces_dir = Path(spaces_dir)

    def _conn(self):
        return _get_conn(self.db_path)

    def save(self, notebook_id: str, graph: KnowledgeGraph) -> None:
        now = utc_now_iso()
        conn = self._conn()
        try:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO knowledge_graphs
                       (notebook_id, nodes, edges, mindmap, generated_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        notebook_id,
                        json.dumps([n.to_dict() for n in graph.nodes], ensure_ascii=False),
                        json.dumps([e.to_dict() for e in graph.edges], ensure_ascii=False),
                        json.dumps(graph.mindmap.to_dict())
                        if graph.mindmap else None,
                        graph.generated_at or "",
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "FOREIGN KEY constraint failed" in str(exc):
                    raise NotebookNotFound(notebook_id) from exc
                raise
            conn.commit()
        finally:
            conn.close()

    def load(self, notebook_id: str) -> Optional[KnowledgeGraph]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM knowledge_graphs WHERE notebook_id = ?",
                (notebook_id,),
            ).fetchone()
            if not row:
                return None
            nodes_data = json.loads(row["nodes"]) if row["nodes"] else []
            edges_data = json.loads(row["edges"]) if row["edges"] else []
            mindmap_data = json.loads(row["mindmap"]) if row["mindmap"] else None
            return KnowledgeGraph.from_dict({
                "nodes": nodes_data,
                "edges": edges_data,
                "mindmap": mindmap_data,
                "generated_at": row["generated_at"],
                "updated_at": row["updated_at"],
            })
        finally:
            conn.close()

    def exists(self, notebook_id: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM knowledge_graphs WHERE notebook_id = ?",
                (notebook_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def delete(self, notebook_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM knowledge_graphs WHERE notebook_id = ?",
                (notebook_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Gap-A retrieval helpers (unchanged — in-memory BFS)
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        notebook_id: str,
        entity_label: str,
        depth: int = 1,
    ) -> List[str]:
        graph = self.load(notebook_id)
        if graph is None or not graph.nodes:
            return []

        label_to_id: Dict[str, str] = {n.label: n.id for n in graph.nodes}
        id_to_label: Dict[str, str] = {n.id: n.label for n in graph.nodes}

        start_id = label_to_id.get(entity_label)
        if start_id is None:
            return []

        adjacency: Dict[str, List[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adjacency and edge.target in adjacency:
                adjacency[edge.source].append(edge.target)
                adjacency[edge.target].append(edge.source)

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
        graph = self.load(notebook_id)
        if graph is None:
            return []
        for node in graph.nodes:
            if node.label == entity_label:
                return list(node.chunk_ids)
        return []
