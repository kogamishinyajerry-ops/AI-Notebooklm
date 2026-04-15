"""
Community Summarizer — V3.0 Gap A Task A-3
==========================================

实现多文档合成引擎的核心能力：
  1. 对知识图谱执行社区检测（Louvain 算法，networkx 内置，无需额外依赖）
  2. 对每个社区生成"主题摘要"（100-200 字），作为"元切片"
  3. 将元切片索引到 ChromaDB（metadata.type = "community_summary"）
  4. 支持"按需重聚类"（方案 Y）：由 /api/v1/knowledge-graph/rebuild 触发

关键设计决策（方案 Y）：
  - 不在每次文档上传时自动重聚类
  - 提供 rebuild() 公开方法，由 API 端点显式调用
  - 聚类结果缓存在 data/communities.json，供前端知识图谱可视化使用
  - 元切片以 community_summary_<N> 为固定 ID 写入 ChromaDB，可幂等重写

C1 合规说明：
  - networkx.community.louvain_communities 是 networkx 内置算法，无外联
  - LLM 调用走已有 call_local_llm（MiniMax，内网部署）
  - 所有文件写入 data/ 目录（Docker 卷挂载）
"""

import json
import logging
import os
import uuid
from typing import List, Dict, Any, Optional

import networkx as nx

from core.llm.client import call_local_llm
from core.retrieval.embeddings import EmbeddingManager
from core.retrieval.vector_store import VectorStoreAdapter
from services.knowledge.graph_builder import KnowledgeGraphBuilder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 社区摘要生成 Prompt
# ---------------------------------------------------------------------------
_SUMMARIZE_SYSTEM = """你是一个专业的航空适航法规知识分析师。
你的任务是分析一组相互关联的适航法规实体，并生成一段简洁的"主题群摘要"。

【要求】
1. 摘要长度：100-200 字（中文）
2. 指明该实体群覆盖的核心适航主题
3. 列举 2-3 个最关键的跨文档依赖关系
4. 输出纯文本，不使用 markdown 标题或列表

【示例输出格式】
本主题群围绕飞控系统失效容限展开，核心涉及 Normal Law、Alternate Law 与飞控计算机
之间的切换逻辑。§ 25.671 与 § 25.1309 在飞控失效场景下形成关键交叉引用关系，
AC 25.1309-1A 进一步规定了定量概率要求。该群还涵盖起飞中断场景下的操纵权限切换，
与 § 25.735 刹车系统要求形成接口约束。
"""


class CommunitySummarizer:
    """
    按需社区检测与摘要引擎（方案 Y）。

    使用方式：
        summarizer = CommunitySummarizer()
        report = summarizer.rebuild()  # 由 API 端点调用
    """

    COMMUNITIES_CACHE = "data/communities.json"
    MIN_COMMUNITY_SIZE = 3    # 少于 N 个节点的社区不生成摘要（噪声过滤）
    MAX_COMMUNITIES = 20      # 最多处理的社区数（防止超大图谱导致 LLM 调用爆炸）
    META_CHUNK_PREFIX = "community_summary_"

    def __init__(self):
        self.graph_builder = KnowledgeGraphBuilder()
        self.embedding_manager = EmbeddingManager()
        self.vector_store = VectorStoreAdapter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild(self) -> Dict[str, Any]:
        """
        完整执行一次社区检测 → 摘要生成 → ChromaDB 索引流程。
        返回本次重建报告（供 API 端点返回给前端）。

        这是方案 Y 的唯一入口，由 POST /api/v1/knowledge-graph/rebuild 触发。
        """
        G = self.graph_builder.graph
        node_count = G.number_of_nodes()
        edge_count = G.number_of_edges()

        if node_count < self.MIN_COMMUNITY_SIZE:
            logger.info("[CommunitySummarizer] 图谱节点数不足，跳过聚类")
            return {
                "status": "skipped",
                "reason": f"图谱节点数 {node_count} < 最小阈值 {self.MIN_COMMUNITY_SIZE}",
                "communities_generated": 0,
            }

        # 1. 社区检测（Louvain，networkx 内置，无额外依赖）
        communities = self._detect_communities(G)
        logger.info(f"[CommunitySummarizer] 检测到 {len(communities)} 个社区（节点总数: {node_count}）")

        # 2. 过滤小社区 + 截断
        filtered = [c for c in communities if len(c) >= self.MIN_COMMUNITY_SIZE]
        filtered = filtered[:self.MAX_COMMUNITIES]
        logger.info(f"[CommunitySummarizer] 过滤后保留 {len(filtered)} 个有效社区")

        # 3. 为每个社区生成摘要并索引到 ChromaDB
        community_records = []
        indexed_count = 0
        failed_count = 0

        for i, community_nodes in enumerate(filtered):
            community_id = i + 1
            try:
                summary = self._generate_summary(community_id, community_nodes, G)
                sources = self._extract_sources(community_nodes, G)

                meta_chunk = {
                    "community_id": community_id,
                    "nodes": list(community_nodes),
                    "node_count": len(community_nodes),
                    "sources": sources,
                    "summary": summary,
                }
                community_records.append(meta_chunk)

                # 写入 ChromaDB（幂等：固定 ID 覆盖写）
                self._upsert_meta_chunk(community_id, summary, sources, community_nodes)
                indexed_count += 1

            except Exception as e:
                logger.error(f"[CommunitySummarizer] 社区 {community_id} 处理失败: {e}")
                failed_count += 1

        # 4. 缓存社区数据（供前端知识图谱可视化）
        self._save_communities_cache(community_records)

        # 5. 标记聚类基线
        self.graph_builder.mark_clustered()

        report = {
            "status": "success",
            "graph_nodes": node_count,
            "graph_edges": edge_count,
            "communities_detected": len(communities),
            "communities_indexed": indexed_count,
            "communities_failed": failed_count,
            "meta_chunks_in_chroma": indexed_count,
        }
        logger.info(f"[CommunitySummarizer] 重建完成: {report}")
        return report

    def get_cached_communities(self) -> List[Dict[str, Any]]:
        """读取缓存的社区数据（供前端可视化，无需重建）。"""
        if not os.path.exists(self.COMMUNITIES_CACHE):
            return []
        try:
            with open(self.COMMUNITIES_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[CommunitySummarizer] 缓存读取失败: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal: Community Detection
    # ------------------------------------------------------------------

    def _detect_communities(self, G: nx.MultiDiGraph) -> List[set]:
        """
        使用 Louvain 算法检测社区。
        networkx >= 3.0 内置 community.louvain_communities，无需 python-louvain。
        对 MultiDiGraph 先转为无向图再聚类（Louvain 要求无向图）。
        """
        # 转为无向简单图（合并多边）
        undirected = nx.Graph(G.to_undirected())

        try:
            # networkx >= 3.0 内置 Louvain
            communities = list(nx.community.louvain_communities(undirected, seed=42))
            return communities
        except AttributeError:
            # 回退到贪心模块度（networkx < 3.0）
            logger.warning("[CommunitySummarizer] louvain_communities 不可用，回退到 greedy_modularity_communities")
            communities = list(nx.community.greedy_modularity_communities(undirected))
            return [set(c) for c in communities]

    # ------------------------------------------------------------------
    # Internal: Summary Generation
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        community_id: int,
        nodes: set,
        G: nx.MultiDiGraph
    ) -> str:
        """
        调用 LLM 生成社区主题摘要。
        向 LLM 提供：节点列表 + 社区内的关键边关系（最多 15 条）。
        """
        node_list = sorted(nodes)[:30]  # 节点过多时截断，避免超出 context

        # 提取社区内部的边关系
        internal_edges = []
        for u, v, data in G.edges(data=True):
            if u in nodes and v in nodes:
                internal_edges.append(f"{u} --[{data.get('relation', '关联')}]--> {v}")
        internal_edges = internal_edges[:15]

        prompt = f"""请分析以下第 {community_id} 号适航法规实体群，生成主题摘要：

【实体节点（{len(node_list)} 个）】
{chr(10).join(f'- {n}' for n in node_list)}

【内部关联关系（{len(internal_edges)} 条）】
{chr(10).join(internal_edges) if internal_edges else '（无内部关系记录）'}

请生成 100-200 字的主题群摘要，重点说明该群覆盖的适航主题及关键跨文档依赖。"""

        try:
            summary = call_local_llm(_SUMMARIZE_SYSTEM, prompt)
            # 基本清洗：去掉前后空白
            summary = summary.strip()
            if not summary or len(summary) < 20:
                return self._fallback_summary(node_list)
            return summary
        except Exception as e:
            logger.error(f"[CommunitySummarizer] LLM 摘要生成失败（社区 {community_id}）: {e}")
            return self._fallback_summary(node_list)

    def _fallback_summary(self, node_list: List[str]) -> str:
        """LLM 失败时的降级摘要（基于节点名拼接）。"""
        top_nodes = ", ".join(node_list[:5])
        return f"本主题群包含 {len(node_list)} 个相关实体，核心节点包括：{top_nodes} 等。该群实体存在跨文档依赖关系，建议结合原始文档进一步分析。"

    # ------------------------------------------------------------------
    # Internal: Source Extraction
    # ------------------------------------------------------------------

    def _extract_sources(self, nodes: set, G: nx.MultiDiGraph) -> List[str]:
        """从图谱边的 source 属性中收集该社区涉及的文档来源。"""
        sources = set()
        for u, v, data in G.edges(data=True):
            if u in nodes or v in nodes:
                src = data.get("source")
                if src:
                    sources.add(src)
        return sorted(sources)

    # ------------------------------------------------------------------
    # Internal: ChromaDB Upsert
    # ------------------------------------------------------------------

    def _upsert_meta_chunk(
        self,
        community_id: int,
        summary: str,
        sources: List[str],
        nodes: set
    ):
        """
        将社区摘要作为元切片写入 ChromaDB。
        使用固定 ID（community_summary_<N>）实现幂等覆写。
        metadata.type = "community_summary" 供检索时识别。
        """
        meta_id = f"{self.META_CHUNK_PREFIX}{community_id}"

        # 先删除旧版本（ChromaDB 不支持 upsert by ID with embeddings，需先 delete）
        try:
            self.vector_store.collection.delete(ids=[meta_id])
        except Exception:
            pass  # 第一次不存在，忽略

        # 生成摘要文本的向量
        embedding = self.embedding_manager.encode([summary])[0].tolist()

        metadata = {
            "type": "community_summary",
            "community_id": str(community_id),
            "sources": json.dumps(sources),       # ChromaDB 要求 str 值
            "node_count": len(nodes),
            "source": "knowledge_graph",          # 保持与普通切片一致的字段名
            "page": "0",
        }

        self.vector_store.collection.add(
            ids=[meta_id],
            embeddings=[embedding],
            documents=[summary],
            metadatas=[metadata],
        )

    # ------------------------------------------------------------------
    # Internal: Cache
    # ------------------------------------------------------------------

    def _save_communities_cache(self, records: List[Dict[str, Any]]):
        """持久化社区数据到 JSON 文件（供前端可视化）。"""
        os.makedirs(os.path.dirname(self.COMMUNITIES_CACHE), exist_ok=True)
        with open(self.COMMUNITIES_CACHE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logger.info(f"[CommunitySummarizer] 社区缓存已写入: {self.COMMUNITIES_CACHE}")
