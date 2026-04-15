import re
import logging
from typing import List, Dict, Any

from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager
from core.retrieval.reranker import CrossEncoderReranker
from services.knowledge.graph_builder import KnowledgeGraphBuilder

logger = logging.getLogger(__name__)


class RetrieverEngine:
    """
    Core RAG Retrieval Engine (Task 7 | V3.0 Task A-2 Graph Expansion Fix)

    修复清单（相对于原始骨架）：
    1. Graph Expansion 不再产出占位字符串 "[Semantic Link to X]"
       改为：用实体名向量检索 ChromaDB，回填真实文档文本
    2. 去重逻辑：用 (source, page, text[:50]) 作为指纹，防止同一 chunk
       被多个实体路径重复引入，污染 Reranker 候选集
    3. 扩展集大小上限：单次 Graph Expansion 最多追加 MAX_EXPANSION_CHUNKS
       个新切片，防止高度节点导致候选集爆炸
    4. 保留 use_graph 开关：允许调用方关闭图谱扩展（如 preview 接口）
    """

    MAX_EXPANSION_CHUNKS = 6  # Graph Expansion 最多追加的切片数

    def __init__(self):
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.reranker = CrossEncoderReranker()
        self.graph_builder = KnowledgeGraphBuilder()

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        final_k: int = 3,
        use_graph: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieves context chunks for a given query.
        Returns a list of dicts: {"text": str, "metadata": dict}

        use_graph=True 时启用知识图谱扩展（默认），
        use_graph=False 时退化为纯向量检索（兼容旧行为）。
        """
        # 1. Embed query
        query_emb = self.embedding_manager.encode([query])[0]

        # 2. Vector Search
        raw_results = self.vector_store.query(
            query_embeddings=query_emb.tolist(), top_k=top_k
        )

        if not raw_results or not raw_results.get("documents") or not raw_results["documents"][0]:
            return []

        # Format results
        formatted_chunks: List[Dict[str, Any]] = []
        for doc, meta in zip(raw_results["documents"][0], raw_results["metadatas"][0]):
            formatted_chunks.append({"text": doc, "metadata": meta})

        # 3. Graph Expansion — 回填真实文本（Task A-2 核心修复）
        if use_graph:
            expanded_chunks = self._graph_expand(query, formatted_chunks)
        else:
            expanded_chunks = formatted_chunks

        # 4. Rerank on expanded set
        best_chunks = self.reranker.rerank(query, expanded_chunks, top_n=final_k)
        return best_chunks

    def _graph_expand(
        self,
        query: str,
        base_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        知识图谱扩展：从基础切片中提取实体，查找相邻节点，
        再将相邻节点的实体名作为查询词去 ChromaDB 回填真实文本。

        关键修复：不再产出 "[Semantic Link to X]" 占位字符串。
        """
        # 已有切片指纹集合（去重用）
        seen: set = set()
        for chunk in base_chunks:
            fp = _chunk_fingerprint(chunk)
            seen.add(fp)

        expanded: List[Dict[str, Any]] = list(base_chunks)
        added_count = 0

        for chunk in base_chunks:
            if added_count >= self.MAX_EXPANSION_CHUNKS:
                break

            # 从切片文本中提取实体候选：§ 条款号 + 2字以上大写缩写
            entities = re.findall(r'§\s*\d+\.\d+[\w.]*|[A-Z]{2,}(?:-\d+)?', chunk["text"])
            # 去重，取前 5 个实体，避免过度查询
            entities = list(dict.fromkeys(entities))[:5]

            for entity in entities:
                if added_count >= self.MAX_EXPANSION_CHUNKS:
                    break

                related_nodes = self.graph_builder.get_related_nodes(entity, depth=1)
                for node in related_nodes:
                    if added_count >= self.MAX_EXPANSION_CHUNKS:
                        break
                    if not node or len(node.strip()) < 2:
                        continue

                    # 用相邻节点名称做向量检索，回填真实文档切片
                    try:
                        node_emb = self.embedding_manager.encode([node])[0]
                        node_results = self.vector_store.query(
                            query_embeddings=node_emb.tolist(), top_k=2
                        )
                    except Exception as e:
                        logger.debug(f"[Retriever] Graph expand query failed for node '{node}': {e}")
                        continue

                    if not node_results.get("documents") or not node_results["documents"][0]:
                        continue

                    for doc, meta in zip(
                        node_results["documents"][0],
                        node_results["metadatas"][0]
                    ):
                        candidate = {"text": doc, "metadata": {**meta, "_graph_expanded": True, "_trigger_entity": entity, "_related_node": node}}
                        fp = _chunk_fingerprint(candidate)
                        if fp not in seen:
                            seen.add(fp)
                            expanded.append(candidate)
                            added_count += 1

        if added_count > 0:
            logger.debug(f"[Retriever] Graph expansion added {added_count} real chunks")

        return expanded

    def get_by_source(self, filename: str, limit: int = 5) -> List[Dict]:
        """Fetches raw chunks for a specific source file (no graph expansion)."""
        results = self.vector_store.collection.get(
            where={"source": filename},
            limit=limit
        )
        processed = []
        if results.get("documents"):
            for i in range(len(results["documents"])):
                processed.append({
                    "text": results["documents"][i],
                    "metadata": results["metadatas"][i]
                })
        return processed


def _chunk_fingerprint(chunk: Dict[str, Any]) -> str:
    """
    生成切片唯一指纹，用于去重。
    用 (source, page, 前50字) 三元组作为标识。
    """
    meta = chunk.get("metadata", {})
    src = str(meta.get("source", ""))
    page = str(meta.get("page", ""))
    text_prefix = chunk.get("text", "")[:50]
    return f"{src}|{page}|{text_prefix}"
