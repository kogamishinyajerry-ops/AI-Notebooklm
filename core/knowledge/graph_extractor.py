"""
core/knowledge/graph_extractor.py
===================================
S-23: Rule-based + frequency-statistical knowledge graph extractor.

No LLM calls, no external services (C1 compliant).

Pipeline
--------
1. Tokenise chunks into candidate entity terms (CJK bigrams + ASCII words)
2. Score by term frequency, filter by whitelist & min-frequency threshold
3. Build co-occurrence edges (shared chunk window)
4. Detect parent-child and definition relations via regex patterns
5. Normalise weights to [0, 1]
6. Build mind-map tree (BFS from highest-weight root, max depth 3)
"""
from __future__ import annotations

import re
import math
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional, Set

from core.models.graph import GraphNode, GraphEdge, MindMapNode, KnowledgeGraph

# ---------------------------------------------------------------------------
# Aerospace / CFD entity whitelist — these always pass the frequency filter
# ---------------------------------------------------------------------------
ENTITY_WHITELIST: Set[str] = {
    # Aircraft & systems
    "C919", "C929", "ARJ21", "COMAC", "CFD", "CAD", "CAE",
    "RANS", "LES", "DNS", "SST", "k-omega", "k-epsilon",
    # Aerodynamics
    "升降舵", "副翼", "方向舵", "翼型", "机翼", "边界层",
    "失速", "配平", "迎角", "攻角", "马赫数", "雷诺数",
    "升力系数", "阻力系数", "俯仰力矩", "压力系数",
    "stall", "trim", "airfoil", "wing", "boundary layer",
    "lift coefficient", "drag coefficient", "pitching moment",
    "angle of attack", "Mach number", "Reynolds number",
    # CFD
    "网格", "湍流", "层流", "分离", "激波", "收敛", "残差",
    "mesh", "turbulence", "laminar", "separation", "shock wave",
    "convergence", "residual",
    # Structural
    "颤振", "疲劳", "稳定性", "操纵性",
    "flutter", "fatigue", "stability", "controllability",
    # Propulsion
    "发动机", "推力", "燃烧室", "涡扇",
    "engine", "thrust", "combustion", "turbofan",
}

# Regex for "X is Y" / "X includes Y" definition-like patterns
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

# Min frequency (non-whitelist terms need at least this many occurrences)
_MIN_FREQ = 2
# Max nodes in the graph
_MAX_NODES = 40
# Max children per mind-map node per level
_MAX_CHILDREN = 6
# Max mind-map depth
_MAX_DEPTH = 3


def _slugify(text: str) -> str:
    """Convert entity text to a stable slug id."""
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
    for entity in ENTITY_WHITELIST:
        if entity.lower() in text.lower() or entity in text:
            terms.append(entity)

    # 2. ASCII multi-word noun phrases (2-3 words, title-case or all-caps)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text):
        terms.append(m.group(1))
    for m in re.finditer(r"\b([A-Z]{2,10})\b", text):
        terms.append(m.group(1))

    # 3. CJK 2-4 gram noun phrases (simple heuristic: consecutive CJK chars)
    for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        terms.append(m.group(0))

    return list(dict.fromkeys(terms))  # preserve order, deduplicate


class GraphExtractor:
    """
    Extracts a KnowledgeGraph from a list of chunk dicts.

    Parameters
    ----------
    chunks:
        List of ``{"text": str, "metadata": dict}`` as returned by
        ``RetrieverEngine.retrieve()`` or directly from ChromaDB.
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
        """
        if not chunks:
            return KnowledgeGraph()

        texts = [c["text"] for c in chunks]

        # 1. Count term frequencies across all chunks
        term_counter: Counter = Counter()
        chunk_terms: List[List[str]] = []
        for text in texts:
            terms = _extract_candidate_terms(text)
            chunk_terms.append(terms)
            term_counter.update(terms)

        # 2. Filter to top entities
        selected = self._select_entities(term_counter)
        if not selected:
            return KnowledgeGraph()

        # 3. Normalise weights
        max_freq = max(term_counter[t] for t in selected)
        nodes: List[GraphNode] = []
        node_by_id: Dict[str, GraphNode] = {}
        for term in selected:
            nid = _slugify(term)
            weight = term_counter[term] / max_freq
            node = GraphNode(id=nid, label=term, weight=round(weight, 4),
                             lang=_detect_lang(term))
            nodes.append(node)
            node_by_id[nid] = node

        # 4. Build co-occurrence edges
        edges = self._build_edges(chunk_terms, selected, node_by_id, term_counter, texts)

        # 5. Build mind-map tree
        mindmap = self._build_mindmap(nodes, edges)

        import datetime
        generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        return KnowledgeGraph(nodes=nodes, edges=edges, mindmap=mindmap,
                               generated_at=generated_at)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_entities(self, counter: Counter) -> List[str]:
        """Filter and rank entities, return top max_nodes."""
        selected = []
        for term, freq in counter.most_common():
            if term in ENTITY_WHITELIST or freq >= self.min_freq:
                if len(term.strip()) >= 2:  # skip single chars
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

        # Co-occurrence edges
        for terms in chunk_terms:
            present = [t for t in terms if t in selected_set]
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    a, b = _slugify(present[i]), _slugify(present[j])
                    if a != b:
                        pair = (min(a, b), max(a, b))
                        cooccur[pair] += 1

        # Normalise co-occurrence weights
        max_cooccur = max(cooccur.values()) if cooccur else 1

        edge_map: Dict[Tuple[str, str], GraphEdge] = {}
        for (src, tgt), cnt in cooccur.most_common(self.max_nodes * 3):
            if src in node_by_id and tgt in node_by_id:
                edge_map[(src, tgt)] = GraphEdge(
                    source=src, target=tgt,
                    relation="co-occurrence",
                    weight=round(cnt / max_cooccur, 4),
                )

        # Structural edges: definition and parent-child patterns
        for text in texts:
            # Definition patterns
            for pattern in _DEFINITION_PATTERNS:
                for m in pattern.finditer(text):
                    a, b = m.group(1).strip(), m.group(2).strip()
                    a_match = self._find_closest_entity(a, selected_set)
                    b_match = self._find_closest_entity(b, selected_set)
                    if a_match and b_match:
                        src, tgt = _slugify(a_match), _slugify(b_match)
                        if src != tgt and src in node_by_id and tgt in node_by_id:
                            pair = (src, tgt)
                            if pair not in edge_map:
                                edge_map[pair] = GraphEdge(
                                    source=src, target=tgt,
                                    relation="definition", weight=0.5,
                                )

            # Parent-child patterns
            for pattern in _PARENT_CHILD_PATTERNS:
                for m in pattern.finditer(text):
                    a, b = m.group(1).strip(), m.group(2).strip()
                    a_match = self._find_closest_entity(a, selected_set)
                    b_match = self._find_closest_entity(b, selected_set)
                    if a_match and b_match:
                        src, tgt = _slugify(a_match), _slugify(b_match)
                        if src != tgt and src in node_by_id and tgt in node_by_id:
                            pair = (src, tgt)
                            if pair not in edge_map:
                                edge_map[pair] = GraphEdge(
                                    source=src, target=tgt,
                                    relation="parent-child", weight=0.6,
                                )

        return list(edge_map.values())

    def _find_closest_entity(self, text: str, entity_set: Set[str]) -> Optional[str]:
        """Return the entity from entity_set that appears in or most closely matches text."""
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
        """
        Build a mind-map tree (BFS, max depth 3) rooted at the highest-weight node.
        """
        if not nodes:
            return None

        # Build adjacency (undirected)
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

            # Sort neighbours by edge weight desc, take top _MAX_CHILDREN
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
