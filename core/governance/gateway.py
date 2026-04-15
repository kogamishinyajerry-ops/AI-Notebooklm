"""
AntiHallucinationGateway — V3.0 Gap C Task C-3
===============================================

三层防御架构最终集成：

  层 1 — 参数类型标注（摄入时）：ParameterRegistry.register_parameters()
          → 已在 services/knowledge/parameter_registry.py 实现

  层 2 — 语义交叉校验（Gateway）：ConstraintChecker._extract_claimed_params()
          + 参数类型核查 ParameterRegistry.verify_claim()
          → 检查 LLM 声称的参数值在注册表中是否类型一致

  层 3 — 工程约束推理（后处理）：ConstraintChecker.check()
          → 规则库校验（W-01/W-02/L-01/V-01/W-03/P-01）

升级要点（相对于 V2.5 Task 43）：
  1. 移除只匹配 3 个参数名的单行正则（para_match），
     改为 ConstraintChecker._extract_claimed_params()，覆盖全部 15 种参数类型。
  2. 层 2 参数类型核查现在遍历所有声称参数，而非只校验第一个匹配项。
  3. 新增层 3 工程约束推理，捕捉跨参数的物理不一致（如 MLW > MTOW）。
  4. 引入 WARN 级别违规：不阻断但记录到日志，前端可展示提示徽章。

C2 合规：所有拦截决策和警告均记录到 logger，可接入审计系统。
"""

import logging
import re
from typing import List, Dict, Any, Tuple

from services.knowledge.parameter_registry import ParameterRegistry, AEROSPACE_PARAM_TAXONOMY
from services.gateway.constraint_checker import ConstraintChecker

logger = logging.getLogger(__name__)


class AntiHallucinationGateway:
    """
    适航知识库反幻觉网关 — V3.0 三层防御集成版。

    使用方式（在 RAG 响应生成后调用）：
        is_valid, response_or_error, citations = AntiHallucinationGateway.validate_and_parse(
            llm_response, contexts
        )
        if not is_valid:
            # response_or_error 是错误原因字符串
            return error_response(response_or_error)
    """

    # Regex to capture <citation src='X' page='Y'>text</citation>
    CITATION_PATTERN = re.compile(
        r'<citation\s+src=[\'"]([^\'"]+)[\'"]\s+page=[\'"]([^\'"]+)[\'"]>(.*?)</citation>',
        re.DOTALL | re.IGNORECASE
    )

    # 单例：摄入阶段已注册的参数表（层 1 数据源）
    _registry = ParameterRegistry()

    # 单例：约束检查器（层 2 提取 + 层 3 规则）
    _checker = ConstraintChecker()

    @classmethod
    def validate_and_parse(
        cls,
        llm_response: str,
        contexts: List[Dict[str, Any]],
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        对 LLM 原始响应执行完整的三层防御校验。

        Args:
            llm_response: LLM 生成的原始响应文本（含 <citation> 标记）
            contexts:     检索器返回的文档上下文切片列表（含 metadata）

        Returns:
            (is_valid, response_or_error, verified_citations)
            - is_valid=True  → 通过，response_or_error 为原始响应
            - is_valid=False → 拦截，response_or_error 为错误消息（不含原始响应）
            - verified_citations: 通过校验的引用列表（供前端渲染引用卡片）
        """
        # ──────────────────────────────────────────────────────────────
        # 层 2 + 层 3：工程约束检查（Citation 解析前执行，尽早拦截）
        # ──────────────────────────────────────────────────────────────
        constraint_result = cls._checker.check(llm_response, contexts)

        if constraint_result.has_blocking_violation:
            error_msg = constraint_result.to_error_message()
            logger.warning(
                f"[Gateway] 层 3 阻断：{error_msg}"
            )
            return False, error_msg, []

        # 收集 WARN 级别违规（不阻断，记录供审计）
        for warn in constraint_result.warnings:
            logger.info(
                f"[Gateway] 层 3 警告 [{warn.rule_id}]: {warn.description}"
            )

        # ──────────────────────────────────────────────────────────────
        # 提取响应中声称的所有参数（层 2 数据准备）
        # ──────────────────────────────────────────────────────────────
        claimed_params_raw = cls._extract_claimed_params_raw(llm_response)
        # claimed_params_raw: {param_type: (value_str, value_float)}

        # ──────────────────────────────────────────────────────────────
        # Citation 校验 + 层 2 参数类型核查
        # ──────────────────────────────────────────────────────────────
        verified_citations = []
        is_fully_verified = True

        for match in cls.CITATION_PATTERN.finditer(llm_response):
            src = match.group(1).strip()
            page = match.group(2).strip()
            content = match.group(3).strip()
            page_int = int(page) if page.isdigit() else 0

            found_in_context = False
            for ctx in contexts:
                ctx_src = str(ctx["metadata"].get("source", ""))
                ctx_page = str(ctx["metadata"].get("page", ""))

                if ctx_src == src and ctx_page == page:
                    found_in_context = True

                    # 层 2：对所有声称参数逐一做注册表类型核查
                    for p_type, (p_val_str, _p_val_float) in claimed_params_raw.items():
                        if not cls._registry.verify_claim(
                            claimed_value=p_val_str,
                            claimed_type=p_type,
                            source=src,
                            page=page_int,
                        ):
                            error_msg = (
                                f"[逻辑幻觉拦截] 引用 {src} P{page} 中的数值 {p_val_str} "
                                f"并非 {p_type}，与摄入时注册的参数类型不符。"
                                f"该引用存在语义偏置，合规审计不通过。"
                            )
                            logger.warning(f"[Gateway] 层 2 阻断：{error_msg}")
                            return False, error_msg, []

                    verified_citations.append({
                        "source_file": src,
                        "page_number": page_int,
                        "content": content,
                        "bbox": ctx["metadata"].get("bbox", [0, 0, 0, 0]),
                    })
                    break  # 同一 citation 匹配到第一个 context 即可

            if not found_in_context:
                is_fully_verified = False
                logger.debug(
                    f"[Gateway] Citation 未能在上下文中找到: src={src} page={page}"
                )

        # 至少有一条已验证引用，且所有引用均在上下文中找到，才视为完全通过
        is_valid = is_fully_verified and len(verified_citations) > 0

        return is_valid, llm_response, verified_citations

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _extract_claimed_params_raw(cls, text: str) -> Dict[str, Tuple[str, float]]:
        """
        从 LLM 响应文本中提取工程参数声称，返回 {类型: (原始值字符串, float)} 字典。

        与 ConstraintChecker._extract_claimed_params() 的区别：
        本方法额外保留原始字符串（p_val_str），供 ParameterRegistry.verify_claim()
        做精确字符串传入（verify_claim 内部做 float 解析）。
        """
        from services.knowledge.parameter_registry import _parse_number

        found: Dict[str, Tuple[str, float]] = {}
        param_names = "|".join(re.escape(k) for k in AEROSPACE_PARAM_TAXONOMY.keys())

        # 模式 1：参数名 + is/为/:/=/≈ + 数值
        pattern1 = re.compile(
            rf'({param_names})\s*(?:is|为|:|=|≈)\s*([\d,\.]+)',
            re.IGNORECASE
        )
        for m in pattern1.finditer(text):
            p_type = m.group(1).strip()
            val_str = m.group(2).replace(",", "").strip()
            val_float = _parse_number(val_str)
            if val_float is not None and p_type not in found:
                found[p_type] = (val_str, val_float)

        # 模式 2：数值 + 单位 + (参数名)
        pattern2 = re.compile(
            rf'([\d,\.]+)\s*(?:kg|kt|lb|psi|kPa|g|kN)?\s*\(?\s*({param_names})\s*\)?',
            re.IGNORECASE
        )
        for m in pattern2.finditer(text):
            val_str = m.group(1).replace(",", "").strip()
            p_type = m.group(2).strip()
            val_float = _parse_number(val_str)
            if val_float is not None and p_type not in found:
                found[p_type] = (val_str, val_float)

        return found
