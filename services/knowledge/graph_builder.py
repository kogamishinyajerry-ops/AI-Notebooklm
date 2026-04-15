import networkx as nx
import os
import json
import pickle
import re
import logging
from typing import List, Tuple, Optional
from core.llm.client import call_local_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Few-Shot Extraction Prompt — 航空适航场景强约束
# ---------------------------------------------------------------------------
_EXTRACTION_SYSTEM = """你是一个高精度的航空适航法规实体关系提取器。
你的任务是从给定的适航条款文本中提取实体三元组 (Subject, Predicate, Object)。

【严格输出格式要求】
- 输出必须是一个 JSON 数组，形如 [["Subject", "Predicate", "Object"], ...]
- 不得输出任何 JSON 以外的内容（无解释，无 markdown 代码块）
- 若无可提取的关系，输出空数组 []

【提取示例 — 请按此格式输出】
输入: "§ 25.954 要求燃油箱防雷击设计必须满足 AC 25.954-1 中的符合性方法。"
输出: [["§ 25.954", "要求满足", "AC 25.954-1"], ["AC 25.954-1", "规定", "燃油箱防雷击设计"]]

输入: "Normal Law 在双发失效时自动切换到 Direct Law，飞控计算机执行该逻辑。"
输出: [["Normal Law", "切换到", "Direct Law"], ["飞控计算机", "执行", "Normal Law 切换逻辑"]]

输入: "See Table 1 for details."
输出: []
"""


def _extract_json_array(text: str) -> Optional[List]:
    """
    从 LLM 响应中鲁棒提取 JSON 数组。
    处理常见的 LLM 输出格式漂移：markdown 代码块、前缀说明文字等。
    """
    # 尝试直接解析
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块提取
    code_block = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if code_block:
        try:
            result = json.loads(code_block.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 尝试提取裸 JSON 数组（最宽松匹配）
    array_match = re.search(r'(\[.*\])', text, re.DOTALL)
    if array_match:
        try:
            result = json.loads(array_match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


class KnowledgeGraphBuilder:
    """
    V3.0 GraphRAG Component (Task 39 | A-1 Hardening)

    改进点（相对于原始骨架）：
    1. Few-Shot Prompt 强约束 LLM 输出格式，减少 JSON 解析失败率
    2. _extract_json_array() 容错解析：处理 markdown 代码块、前缀文字等漂移
    3. 单条 triple 粒度异常隔离：跳过格式错误项，不放弃整块
    4. 批量写盘策略：每 SAVE_BATCH_SIZE 条 chunk 保存一次，减少 IO 热点
    5. 节点数变化记录：供 community_summarizer 判断是否需要重聚类
    """

    SAVE_BATCH_SIZE = 10  # 每处理 N 个 chunk 才持久化一次

    def __init__(self, persist_path: str = "data/knowledge_graph.gpickle"):
        self.persist_path = persist_path
        self._unsaved_count = 0
        self._node_count_at_last_cluster = 0

        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, 'rb') as f:
                    self.graph = pickle.load(f)
                logger.info(f"[GraphBuilder] 已加载知识图谱: {self.graph.number_of_nodes()} 节点, "
                            f"{self.graph.number_of_edges()} 边")
            except Exception as e:
                logger.warning(f"[GraphBuilder] 图谱加载失败，重建空图: {e}")
                self.graph = nx.MultiDiGraph()
        else:
            self.graph = nx.MultiDiGraph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_chunk(self, chunk_id: str, text: str, source: str) -> int:
        """
        使用 Few-Shot LLM 提取实体三元组并写入图谱。
        返回本次成功提取的 triple 数量（用于监控）。
        """
        if not text or len(text.strip()) < 20:
            return 0

        prompt = f"请从以下航空适航文本中提取实体关系三元组：\n\n{text[:1500]}"

        try:
            raw_response = call_local_llm(_EXTRACTION_SYSTEM, prompt)
        except Exception as e:
            logger.error(f"[GraphBuilder] LLM 调用失败 chunk={chunk_id}: {e}")
            return 0

        triples = _extract_json_array(raw_response)
        if triples is None:
            logger.warning(f"[GraphBuilder] JSON 解析彻底失败 chunk={chunk_id}，跳过。"
                           f" LLM原始响应前200字: {raw_response[:200]}")
            return 0

        success_count = 0
        for item in triples:
            # 单条 triple 粒度隔离：格式错误不影响其他条
            try:
                if not (isinstance(item, (list, tuple)) and len(item) == 3):
                    continue
                s, p, o = str(item[0]).strip(), str(item[1]).strip(), str(item[2]).strip()
                if not s or not p or not o:
                    continue

                self.graph.add_node(s, type="entity")
                self.graph.add_node(o, type="entity")
                self.graph.add_edge(s, o, relation=p, source=source, chunk_id=chunk_id)
                success_count += 1
            except Exception as e:
                logger.debug(f"[GraphBuilder] 单条 triple 跳过: {item} — {e}")

        if success_count > 0:
            self._unsaved_count += 1
            if self._unsaved_count >= self.SAVE_BATCH_SIZE:
                self._save()
                self._unsaved_count = 0

        return success_count

    def flush(self):
        """强制将未保存的变更写盘（供 ingestion pipeline 在完成时调用）。"""
        if self._unsaved_count > 0:
            self._save()
            self._unsaved_count = 0

    def needs_reclustering(self, threshold: int = 20) -> bool:
        """
        判断自上次聚类以来新增节点是否超过阈值。
        供 community_summarizer 决策是否需要重聚类（方案 Y 的核心判断逻辑）。
        """
        current = self.graph.number_of_nodes()
        delta = current - self._node_count_at_last_cluster
        return delta >= threshold

    def mark_clustered(self):
        """记录当前聚类时的节点基线。"""
        self._node_count_at_last_cluster = self.graph.number_of_nodes()

    def get_related_nodes(self, entity_name: str, depth: int = 1) -> List[str]:
        """
        BFS 查找相关节点（保持原有接口不变）。
        改进：返回节点名而非对象引用，并限制最大返回数量避免爆炸。
        """
        if entity_name not in self.graph:
            return []

        related = set()
        current_nodes = {entity_name}
        for _ in range(depth):
            next_nodes = set()
            for node in current_nodes:
                if node in self.graph:
                    for neighbor in self.graph.neighbors(node):
                        if neighbor != entity_name:
                            related.add(neighbor)
                            next_nodes.add(neighbor)
            current_nodes = next_nodes

        # 限制最大返回 20 个，防止高度节点导致检索爆炸
        return list(related)[:20]

    def get_stats(self) -> dict:
        """返回图谱统计信息，供 API 端点展示。"""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "unsaved_chunks": self._unsaved_count,
            "needs_reclustering": self.needs_reclustering(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self):
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
        tmp_path = self.persist_path + ".tmp"
        with open(tmp_path, 'wb') as f:
            pickle.dump(self.graph, f)
        os.replace(tmp_path, self.persist_path)  # 原子替换，防止写入中途崩溃导致图谱损坏
        logger.debug(f"[GraphBuilder] 图谱已持久化: {self.graph.number_of_nodes()} 节点")
