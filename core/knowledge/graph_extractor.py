"""
core/knowledge/graph_extractor.py
===================================
S-23 + Gap-C/A: Rule-based + frequency-statistical knowledge graph extractor.

Changes vs S-23 baseline:
  * ENTITY_WHITELIST imported from entity_whitelist.py (domain-structured,
    ~350 terms across CFD / Airworthiness / Safety)
  * Each GraphNode now carries a `chunk_ids` list (reverse-index: entity →
    source chunks).  This is consumed by GraphStore.get_source_chunks() for
    Graph Expansion retrieval (Gap-A).
  * New public method `identify_entities(text)` — returns the whitelist terms
    found in a text string.  Used by RetrieverEngine._graph_expand().

No LLM calls, no external services (C1 compliant).
"""
from __future__ import annotations

import re
import datetime
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional, Set

from core.models.graph import GraphNode, GraphEdge, MindMapNode, KnowledgeGraph
from core.knowledge.entity_whitelist import ENTITY_WHITELIST

# ---------------------------------------------------------------------------
# Re-export so callers can still do:
#   from core.knowledge.graph_extractor import ENTITY_WHITELIST
# ---------------------------------------------------------------------------
__all__ = ["GraphExtractor", "ENTITY_WHITELIST"]

# ---------------------------------------------------------------------------
# Regex for "X is Y" / "X includes Y" definition-like patterns
# ---------------------------------------------------------------------------
_DEFINITION_PATTERNS = [
    re.compile(r"(.+?)是(.+?)的", re.UNICODE),
    re.compile(r"(.+?)包括(.+)", re.UNICODE),
    re.compile(r"(.+?) is (?:a|an|the) (.+)", re.IGNORECASE),
    re.compile(r"(.+?) refers to (.+)", re.IGNORECASE),
]

_PARENT_CHILD_PATTERNS = [
    re.compile(r"(.+?)的(.+?)(?:系统|模块|组件|参数|特性)", re.UNICODE),
    re.compile(r"(.+?) (?:subsystem|module|component|parameter) of (.+)", re.IGNORECASE),
]

_MIN_FREQ = 2
_MAX_NODES = 40
_MAX_CHILDREN = 6
_MAX_DEPTH = 3


def _slugify(text: str) -> str:
    return re.sub(r"[^\w]", "_", text.strip().lower())[:64]


def _detect_lang(text: str) -> str:
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_ascii = bool(re.search(r"[a-zA-Z]", text))
    if has_cjk and has_ascii:
        return "mixed"
    if has_cjk:
        return "zh"
    return "en"


def _extract_candidate_terms(text: str) -> List[str]:
    """
    Extract candidate entity terms from a text block.
    Returns de-duplicated list of candidate strings.
    """
    terms: List[str] = []

    # 1. Whitelist scan (case-insensitive for ASCII terms)
    text_lower = text.lower()
    for entity in ENTITY_WHITELIST:
        if entity.lower() in text_lower or entity in text:
            terms.append(entity)

    # 2. ASCII multi-word noun phrases (2-3 words, title-case or all-caps)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text):
        terms.append(m.group(1))
    for m in re.finditer(r"\b([A-Z]{2,10})\b", text):
        terms.append(m.group(1))

    # 3. CJK 2-4 gram noun phrases
    for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        terms.append(m.group(0))

    return list(dict.fromkeys(terms))  # preserve order, deduplicate


class GraphExtractor:
    """
    Extracts a KnowledgeGraph from a list of chunk dicts.

    Parameters
    ----------
    chunks:
        List of ``{"text": str, "metadata": dict}`` — the ``"id"`` key
        in metadata (if present) is recorded in the entity→chunk_ids
        reverse-index.
    max_nodes:
        Maximum number of nodes in the output graph.
    min_freq:
        Minimum term frequency for non-whitelist entities.
    """

    def __init__(
        self,
        max_nodes: int = _MAX_NODES,
        min_freq: int = _MIN_FREQ,
    ) -> None:
        self.max_nodes = max_nodes
        self.min_freq = min_freq

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, chunks: List[Dict]) -> KnowledgeGraph:
        """
        Full extraction pipeline: entities → edges → mindmap.
        Each GraphNode now carries ``chunk_ids`` for Gap-A retrieval.
        """
        if not chunks:
            return KnowledgeGraph()

        texts = [c["text"] for c in chunks]
        # chunk_id is taken from metadata["id"] if present, else positional index
        chunk_ids = [c.get("metadata", {}).get("id", str(i)) for i, c in enumerate(chunks)]

        # 1. Count term frequencies + build entity→chunk_ids reverse-index
        term_counter: Counter = Counter()
        chunk_terms: List[List[str]] = []
        entity_to_chunks: Dict[str, List[str]] = defaultdict(list)

        for idx, text in enumerate(texts):
            terms = _extract_candidate_terms(text)
            chunk_terms.append(terms)
            term_counter.update(terms)
            for term in set(terms):  # deduplicate per chunk
                entity_to_chunks[term].append(chunk_ids[idx])

        # 2. Filter to top entities
        selected = self._select_entities(term_counter)
        if not selected:
            return KnowledgeGraph()

        # 3. Normalise weights & build GraphNodes with chunk_ids
        max_freq = max(term_counter[t] for t in selected)
        nodes: List[GraphNode] = []
        node_by_id: Dict[str, GraphNode] = {}
        for term in selected:
            nid = _slugify(term)
            weight = term_counter[term] / max_freq
            node = GraphNode(
                id=nid,
                label=term,
                weight=round(weight, 4),
                lang=_detect_lang(term),
                chunk_ids=list(dict.fromkeys(entity_to_chunks.get(term, []))),
            )
            nodes.append(node)
            node_by_id[nid] = node

        # 4. Build co-occurrence edges
        edges = self._build_edges(chunk_terms, selected, node_by_id, term_counter, texts)

        # 5. Build mind-map tree
        mindmap = self._build_mindmap(nodes, edges)

        generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        return KnowledgeGraph(
            nodes=nodes,
            edges=edges,
            mindmap=mindmap,
            generated_at=generated_at,
        )

    def identify_entities(self, text: str) -> List[str]:
        """
        Return the whitelist entities found in *text*.

        Used by RetrieverEngine._graph_expand() to identify query entities
        before looking up their associated chunks in GraphStore.

        C1 compliant — purely string-matching, no model calls.
        """
        text_lower = text.lower()
        found: List[str] = []
        for entity in ENTITY_WHITELIST:
            if entity.lower() in text_lower or entity in text:
                found.append(entity)
        return found

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_entities(self, counter: Counter) -> List[str]:
        selected = []
        for term, freq in counter.most_common():
            if term in ENTITY_WHITELIST or freq >= self.min_freq:
                if len(term.strip()) >= 2:
                    selected.append(term)
            if len(selected) >= self.max_nodes:
                break
        return selected

    def _build_edges(
        self,
        chunk_terms: List[List[str]],
        selected: List[str],
        node_by_id: Dict[str, GraphNode],
        term_counter: Counter,
        texts: List[str],
    ) -> List[GraphEdge]:
        selected_set = set(selected)
        cooccur: Counter = Counter()

        for terms in chunk_terms:
            present = [t for t in terms if t in selected_set]
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    a, b = _slugify(present[i]), _slugify(present[j])
                    if a != b:
                        pair = (min(a, b), max(a, b))
                        cooccur[pair] += 1

        max_cooccur = max(cooccur.values()) if cooccur else 1

        edge_map: Dict[Tuple[str, str], GraphEdge] = {}
        for (src, tgt), cnt in cooccur.most_common(self.max_nodes * 3):
            if src in node_by_id and tgt in node_by_id:
                edge_map[(src, tgt)] = GraphEdge(
                    source=src, target=tgt,
                    relation="co-occurrence",
                    weight=round(cnt / max_cooccur, 4),
                )

        for text in texts:
            for pattern in _DEFINITION_PATTERNS:
                for m in pattern.finditer(text):
                    a, b = m.group(1).strip(), m.group(2).strip()
                    a_m = self._find_closest_entity(a, selected_set)
                    b_m = self._find_closest_entity(b, selected_set)
                    if a_m and b_m:
                        src, tgt = _slugify(a_m), _slugify(b_m)
                        if src != tgt and src in node_by_id and tgt in node_by_id:
                            edge_map.setdefault((src, tgt), GraphEdge(
                                source=src, target=tgt,
                                relation="definition", weight=0.5,
                            ))

            for pattern in _PARENT_CHILD_PATTERNS:
                for m in pattern.finditer(text):
                    a, b = m.group(1).strip(), m.group(2).strip()
                    a_m = self._find_closest_entity(a, selected_set)
                    b_m = self._find_closest_entity(b, selected_set)
                    if a_m and b_m:
                        src, tgt = _slugify(a_m), _slugify(b_m)
                        if src != tgt and src in node_by_id and tgt in node_by_id:
                            edge_map.setdefault((src, tgt), GraphEdge(
                                source=src, target=tgt,
                                relation="parent-child", weight=0.6,
                            ))

        return list(edge_map.values())

    def _find_closest_entity(self, text: str, entity_set: Set[str]) -> Optional[str]:
        text_lower = text.lower()
        for entity in entity_set:
            if entity.lower() in text_lower or text_lower in entity.lower():
                return entity
        return None

    def _build_mindmap(
        self,
        nodes: List[GraphNode],
        edges: List[GraphEdge],
    ) -> Optional[MindMapNode]:
        if not nodes:
            return None

        adjacency: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source].append((edge.target, edge.weight))
            adjacency[edge.target].append((edge.source, edge.weight))

        node_by_id = {n.id: n for n in nodes}
        root_node = max(nodes, key=lambda n: n.weight)

        def _build(node_id: str, visited: Set[str], depth: int) -> MindMapNode:
            visited.add(node_id)
            n = node_by_id[node_id]
            mm = MindMapNode(id=n.id, label=n.label, weight=n.weight)
            if depth >= _MAX_DEPTH:
                return mm

            neighbours = sorted(
                [(nid, w) for nid, w in adjacency[node_id] if nid not in visited],
                key=lambda x: x[1],
                reverse=True,
            )[:_MAX_CHILDREN]

            for child_id, _ in neighbours:
                child_mm = _build(child_id, visited.copy(), depth + 1)
                mm.children.append(child_mm)

            return mm

        return _build(root_node.id, set(), 0)
