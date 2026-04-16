"""
core/models/graph.py
====================
Data models for S-23 Mind Map / Knowledge Graph Lite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class GraphNode:
    id: str          # slug of entity text
    label: str       # display text
    weight: float    # 0.0-1.0 normalised frequency
    lang: str = "mixed"  # "zh" | "en" | "mixed"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "label": self.label, "weight": self.weight, "lang": self.lang}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphNode":
        return cls(id=d["id"], label=d["label"], weight=d["weight"], lang=d.get("lang", "mixed"))


@dataclass
class GraphEdge:
    source: str      # node id
    target: str      # node id
    relation: str    # "co-occurrence" | "parent-child" | "definition"
    weight: float    # normalised co-occurrence count

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "target": self.target,
                "relation": self.relation, "weight": self.weight}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphEdge":
        return cls(source=d["source"], target=d["target"],
                   relation=d["relation"], weight=d["weight"])


@dataclass
class MindMapNode:
    id: str
    label: str
    weight: float
    children: List["MindMapNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "weight": self.weight,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MindMapNode":
        children = [cls.from_dict(c) for c in d.get("children", [])]
        return cls(id=d["id"], label=d["label"], weight=d["weight"], children=children)


@dataclass
class KnowledgeGraph:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    mindmap: MindMapNode | None = None
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "mindmap": self.mindmap.to_dict() if self.mindmap else None,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KnowledgeGraph":
        return cls(
            nodes=[GraphNode.from_dict(n) for n in d.get("nodes", [])],
            edges=[GraphEdge.from_dict(e) for e in d.get("edges", [])],
            mindmap=MindMapNode.from_dict(d["mindmap"]) if d.get("mindmap") else None,
            generated_at=d.get("generated_at", ""),
        )
