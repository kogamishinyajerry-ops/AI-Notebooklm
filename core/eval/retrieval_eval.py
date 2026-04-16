from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence

if TYPE_CHECKING:
    from core.models.graph import KnowledgeGraph
    from core.retrieval.retriever import RetrieverEngine


DEFAULT_NOTEBOOK_ID = "__eval__"


@dataclass
class RetrievalEvalCase:
    query: str
    expected_pages: List[int] = field(default_factory=list)
    expected_keywords: List[str] = field(default_factory=list)
    note: str | None = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RetrievalEvalCase":
        return cls(
            query=str(payload["query"]),
            expected_pages=[int(page) for page in payload.get("expected_pages", [])],
            expected_keywords=[str(item) for item in payload.get("expected_keywords", [])],
            note=payload.get("note"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalEvalHit:
    rank: int
    page: int | None
    matched_keywords: List[str]
    text_preview: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalEvalResult:
    query: str
    hit: bool
    page_hit: bool
    keyword_hit: bool
    first_hit_rank: int | None
    reciprocal_rank: float
    matched_pages: List[int]
    matched_keywords: List[str]
    top_results: List[Dict[str, Any]]
    hits: List[RetrievalEvalHit]
    note: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["hits"] = [item.to_dict() for item in self.hits]
        return payload


class InMemoryGraphStore:
    """Small graph-store adapter for evaluation runs."""

    def __init__(self, graphs: Optional[Dict[str, Any]] = None) -> None:
        self.graphs = graphs or {}

    def save(self, notebook_id: str, graph: Any) -> None:
        self.graphs[notebook_id] = graph

    def load(self, notebook_id: str) -> Optional[Any]:
        return self.graphs.get(notebook_id)

    def get_neighbors(
        self,
        notebook_id: str,
        entity_label: str,
        depth: int = 1,
    ) -> List[str]:
        graph = self.load(notebook_id)
        if graph is None or not graph.nodes:
            return []

        label_to_id = {node.label: node.id for node in graph.nodes}
        id_to_label = {node.id: node.label for node in graph.nodes}
        start_id = label_to_id.get(entity_label)
        if start_id is None:
            return []

        adjacency: Dict[str, List[str]] = {node.id: [] for node in graph.nodes}
        for edge in graph.edges:
            if edge.source in adjacency and edge.target in adjacency:
                adjacency[edge.source].append(edge.target)
                adjacency[edge.target].append(edge.source)

        visited = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        result: List[str] = []

        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbour_id in adjacency.get(node_id, []):
                if neighbour_id in visited:
                    continue
                visited.add(neighbour_id)
                result.append(id_to_label[neighbour_id])
                queue.append((neighbour_id, current_depth + 1))

        return result

    def get_source_chunks(self, notebook_id: str, entity_label: str) -> List[str]:
        graph = self.load(notebook_id)
        if graph is None:
            return []

        for node in graph.nodes:
            if node.label == entity_label:
                return list(node.chunk_ids)
        return []


def load_eval_cases(path: str | Path) -> List[RetrievalEvalCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [RetrievalEvalCase.from_dict(item) for item in payload]


def weight_grid(step: float = 0.1) -> List[Dict[str, float]]:
    if step <= 0 or step > 1:
        raise ValueError("step must be in the range (0, 1]")

    scale = round(1 / step)
    if abs((step * scale) - 1.0) > 1e-9:
        raise ValueError("step must evenly divide 1.0")

    combos: List[Dict[str, float]] = []
    for semantic in range(scale + 1):
        for bm25 in range(scale + 1 - semantic):
            graph = scale - semantic - bm25
            if semantic == 0 and bm25 == 0 and graph == 0:
                continue
            combos.append(
                {
                    "semantic": round(semantic / scale, 4),
                    "bm25": round(bm25 / scale, 4),
                    "graph": round(graph / scale, 4),
                }
            )
    return combos


def build_eval_corpus(
    vector_rows: Dict[str, Sequence[Any]],
) -> List[Dict[str, Any]]:
    ids = list(vector_rows.get("ids") or [])
    documents = list(vector_rows.get("documents") or [])
    metadatas = list(vector_rows.get("metadatas") or [])

    corpus: List[Dict[str, Any]] = []
    for index, (doc, meta) in enumerate(zip(documents, metadatas)):
        metadata = dict(meta or {})
        metadata.setdefault("id", ids[index] if index < len(ids) else str(index))
        corpus.append({"text": str(doc), "metadata": metadata})
    return corpus


def prepare_retriever_for_eval(
    retriever: Optional["RetrieverEngine"] = None,
    *,
    where: dict | None = None,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
    build_graph: bool = True,
) -> tuple["RetrieverEngine", List[Dict[str, Any]]]:
    from core.knowledge.graph_extractor import GraphExtractor
    from core.retrieval.retriever import RetrieverEngine

    engine = retriever or RetrieverEngine()
    vector_rows = engine.vector_store.get_all(where=where)
    corpus_rows = build_eval_corpus(vector_rows)
    engine.rebuild_bm25([(row["text"], row["metadata"]) for row in corpus_rows])

    if build_graph:
        extractor = GraphExtractor()
        graph_store = InMemoryGraphStore()
        graph_store.save(notebook_id, extractor.extract(corpus_rows))
        engine.graph_extractor = extractor
        engine.graph_store = graph_store

    return engine, corpus_rows


def _match_case(
    case: RetrievalEvalCase,
    results: Sequence[Dict[str, Any]],
) -> RetrievalEvalResult:
    expected_pages = set(case.expected_pages)
    expected_keywords = [item.lower() for item in case.expected_keywords]

    hits: List[RetrievalEvalHit] = []
    matched_pages: List[int] = []
    matched_keywords: List[str] = []

    for rank, result in enumerate(results, start=1):
        metadata = result.get("metadata", {}) or {}
        page = metadata.get("page")
        try:
            page_value = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_value = None
        text = str(result.get("text", ""))
        text_lower = text.lower()
        keyword_hits = [
            keyword
            for keyword in expected_keywords
            if keyword and keyword in text_lower
        ]
        page_hit = page_value in expected_pages if page_value is not None else False
        if not page_hit and not keyword_hits:
            continue

        if page_hit and page_value is not None and page_value not in matched_pages:
            matched_pages.append(page_value)
        for keyword in keyword_hits:
            if keyword not in matched_keywords:
                matched_keywords.append(keyword)
        hits.append(
            RetrievalEvalHit(
                rank=rank,
                page=page_value,
                matched_keywords=keyword_hits,
                text_preview=text[:200],
            )
        )

    first_hit_rank = hits[0].rank if hits else None
    return RetrievalEvalResult(
        query=case.query,
        hit=bool(hits),
        page_hit=bool(matched_pages),
        keyword_hit=bool(matched_keywords),
        first_hit_rank=first_hit_rank,
        reciprocal_rank=(1.0 / first_hit_rank) if first_hit_rank else 0.0,
        matched_pages=matched_pages,
        matched_keywords=matched_keywords,
        top_results=[
            {
                "rank": rank,
                "page": (result.get("metadata", {}) or {}).get("page"),
                "source": (result.get("metadata", {}) or {}).get("source"),
                "text_preview": str(result.get("text", ""))[:200],
            }
            for rank, result in enumerate(results, start=1)
        ],
        hits=hits,
        note=case.note,
    )


def evaluate_cases(
    retriever: Any,
    cases: Sequence[RetrievalEvalCase],
    *,
    top_k: int = 8,
    final_k: int = 5,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
    source_ids: Optional[List[str]] = None,
    expand_graph: bool = True,
    rrf_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    results: List[RetrievalEvalResult] = []

    for case in cases:
        retrieved = retriever.retrieve(
            case.query,
            top_k=top_k,
            final_k=final_k,
            source_ids=source_ids,
            notebook_id=notebook_id,
            expand_graph=expand_graph,
            rrf_weights=rrf_weights,
        )
        results.append(_match_case(case, retrieved))

    total = len(results)
    hits = sum(1 for result in results if result.hit)
    top1_hits = sum(1 for result in results if result.first_hit_rank == 1)
    page_hits = sum(1 for result in results if result.page_hit)
    keyword_hits = sum(1 for result in results if result.keyword_hit)
    mrr = round(sum(result.reciprocal_rank for result in results) / total, 4) if total else 0.0

    return {
        "summary": {
            "queries": total,
            "hit_rate": round(hits / total, 4) if total else 0.0,
            "top1_hit_rate": round(top1_hits / total, 4) if total else 0.0,
            "page_hit_rate": round(page_hits / total, 4) if total else 0.0,
            "keyword_hit_rate": round(keyword_hits / total, 4) if total else 0.0,
            "mrr": mrr,
            "top_k": top_k,
            "final_k": final_k,
            "expand_graph": expand_graph,
            "rrf_weights": rrf_weights,
        },
        "results": [result.to_dict() for result in results],
    }


def evaluate_weight_grid(
    retriever: Any,
    cases: Sequence[RetrievalEvalCase],
    *,
    candidates: Optional[Iterable[Dict[str, float]]] = None,
    top_k: int = 8,
    final_k: int = 5,
    notebook_id: str = DEFAULT_NOTEBOOK_ID,
    source_ids: Optional[List[str]] = None,
    expand_graph: bool = True,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for weights in candidates or weight_grid():
        report = evaluate_cases(
            retriever,
            cases,
            top_k=top_k,
            final_k=final_k,
            notebook_id=notebook_id,
            source_ids=source_ids,
            expand_graph=expand_graph,
            rrf_weights=weights,
        )
        ranked.append(
            {
                "weights": weights,
                **report["summary"],
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["mrr"],
            -item["hit_rate"],
            -item["top1_hit_rate"],
            -item["page_hit_rate"],
        )
    )
    return ranked


def write_json_report(path: str | Path, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
