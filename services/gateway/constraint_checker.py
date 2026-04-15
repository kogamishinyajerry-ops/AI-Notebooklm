"""
ConstraintChecker — V3.0 Gap C Task C-2
=========================================

工程约束推理后处理器：Gap C 的第二、三层防御。

三层防御架构（系统提示定义）：
  层 1 — 参数类型标注（摄入时）：ParameterRegistry.register_parameters()
  层 2 — 语义交叉校验（Gateway）：ConstraintChecker.semantic_cross_check()
  层 3 — 工程约束推理（后处理）：ConstraintChecker.engineering_constraint_check()

本文件实现层 2 和层 3。

层 2 — 语义交叉校验：
  检测 LLM 响应中的参数声称是否内部一致。
  例：若 LLM 同时声称 MTOW=72500 且 MLW=75000，
  而 MLW > MTOW 违反航空基本约束（着陆重量不得超过起飞重量），则拦截。

层 3 — 工程约束推理：
  基于已知航空工程关系进行推理验证。
  例：若 n_ult 被声称为 2.5，但 FAR/CS-25 规定 n_ult ≥ 1.5 × n_lim，
  且 n_lim 已注册为 2.5，则 n_ult 应 ≥ 3.75，声称值 2.5 被拦截。

C2 合规：所有校验结果记录到违规日志，供溯源审计。
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 航空工程约束规则库
# ---------------------------------------------------------------------------

@dataclass
class ConstraintViolation:
    """单条约束违规记录。"""
    rule_id: str
    description: str
    claimed_params: Dict[str, float]
    expected: str
    severity: str  # "BLOCK" | "WARN"


@dataclass
class CheckResult:
    """约束检查总结果。"""
    passed: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[ConstraintViolation] = field(default_factory=list)

    @property
    def has_blocking_violation(self) -> bool:
        return any(v.severity == "BLOCK" for v in self.violations)

    def to_error_message(self) -> str:
        blocks = [v for v in self.violations if v.severity == "BLOCK"]
        if not blocks:
            return ""
        parts = []
        for v in blocks:
            parts.append(f"[{v.rule_id}] {v.description}（期望: {v.expected}）")
        return "[工程约束违规] " + "；".join(parts)


# 工程约束规则定义
# 格式：(rule_id, description, check_func, severity)
# check_func(params: Dict[str, float]) -> Optional[ConstraintViolation]

def _rule_mlw_leq_mtow(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """MLW ≤ MTOW（着陆重量不超过起飞重量）"""
    if "MLW" in params and "MTOW" in params:
        if params["MLW"] > params["MTOW"] * 1.001:  # 0.1% 容差
            return ConstraintViolation(
                rule_id="W-01",
                description=f"MLW({params['MLW']:.0f}) > MTOW({params['MTOW']:.0f})，违反重量层级约束",
                claimed_params={"MLW": params["MLW"], "MTOW": params["MTOW"]},
                expected="MLW ≤ MTOW",
                severity="BLOCK",
            )
    return None


def _rule_mzfw_leq_mlw(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """MZFW ≤ MLW（通常成立；若 MLW 未声称则跳过）"""
    if "MZFW" in params and "MLW" in params:
        if params["MZFW"] > params["MLW"] * 1.001:
            return ConstraintViolation(
                rule_id="W-02",
                description=f"MZFW({params['MZFW']:.0f}) > MLW({params['MLW']:.0f})，违反重量层级约束",
                claimed_params={"MZFW": params["MZFW"], "MLW": params["MLW"]},
                expected="MZFW ≤ MLW",
                severity="BLOCK",
            )
    return None


def _rule_n_ult_geq_1p5_n_lim(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """n_ult ≥ 1.5 × n_lim（FAR/CS-25 §25.303 安全系数）"""
    if "n_ult" in params and "n_lim" in params:
        expected_min = params["n_lim"] * 1.5
        if params["n_ult"] < expected_min * 0.99:  # 1% 容差
            return ConstraintViolation(
                rule_id="L-01",
                description=(
                    f"n_ult({params['n_ult']:.2f}) < 1.5 × n_lim({params['n_lim']:.2f}) = "
                    f"{expected_min:.2f}，违反 §25.303 安全系数要求"
                ),
                claimed_params={"n_ult": params["n_ult"], "n_lim": params["n_lim"]},
                expected=f"n_ult ≥ {expected_min:.2f}",
                severity="BLOCK",
            )
    return None


def _rule_vmo_positive(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """Vmo > 0（速度不为负）"""
    if "Vmo" in params and params["Vmo"] <= 0:
        return ConstraintViolation(
            rule_id="V-01",
            description=f"Vmo({params['Vmo']}) ≤ 0，速度参数无效",
            claimed_params={"Vmo": params["Vmo"]},
            expected="Vmo > 0",
            severity="BLOCK",
        )
    return None


def _rule_mtow_range(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """MTOW 合理范围：1,000 kg ~ 600,000 kg（覆盖 C919 至 A380）"""
    if "MTOW" in params:
        v = params["MTOW"]
        if not (1_000 <= v <= 600_000):
            return ConstraintViolation(
                rule_id="W-03",
                description=f"MTOW({v:.0f} kg) 超出合理范围 [1,000–600,000 kg]",
                claimed_params={"MTOW": v},
                expected="1,000 ≤ MTOW ≤ 600,000 kg",
                severity="WARN",
            )
    return None


def _rule_pcab_range(params: Dict[str, float]) -> Optional[ConstraintViolation]:
    """P_cab 合理范围：0 ~ 100 psi"""
    if "P_cab" in params:
        v = params["P_cab"]
        if not (0 < v <= 100):
            return ConstraintViolation(
                rule_id="P-01",
                description=f"P_cab({v} psi) 超出合理范围 (0, 100] psi",
                claimed_params={"P_cab": v},
                expected="0 < P_cab ≤ 100 psi",
                severity="WARN",
            )
    return None


# 规则集
_CONSTRAINT_RULES = [
    _rule_mlw_leq_mtow,
    _rule_mzfw_leq_mlw,
    _rule_n_ult_geq_1p5_n_lim,
    _rule_vmo_positive,
    _rule_mtow_range,
    _rule_pcab_range,
]

# 参数提取正则（从 LLM 响应文本中提取数值声称）
_PARAM_CLAIM_PATTERNS = [
    # "MTOW is 72,500" / "MTOW 为 72500" / "MTOW: 72500"
    (r'(MTOW|MZFW|MLW|OEW|Vmo|Mmo|Vfe|Vle|Vs|n_lim|n_ult|P_cab|T_max)',
     r'\s*(?:is|为|:|=)\s*([\d,\.]+)'),
    # "72,500 kg (MTOW)"
    (r'([\d,\.]+)\s*(?:kg|kt|lb|psi)\s*\(?(MTOW|MZFW|MLW|OEW|Vmo|n_lim|n_ult|P_cab)\)?',
     None),
]


# ---------------------------------------------------------------------------
# ConstraintChecker 主类
# ---------------------------------------------------------------------------

class ConstraintChecker:
    """
    工程约束检查器：实现 Gap C 的第二层（语义交叉校验）和第三层（工程约束推理）防御。

    使用方式（在 AntiHallucinationGateway 中调用）：
        checker = ConstraintChecker()
        result = checker.check(llm_response, contexts)
        if result.has_blocking_violation:
            return False, result.to_error_message(), []
    """

    def check(
        self,
        llm_response: str,
        contexts: List[Dict],
    ) -> CheckResult:
        """
        对 LLM 响应执行完整的约束检查。

        层 2：从响应文本中提取所有参数声称，检查内部语义一致性
        层 3：对提取的参数集应用工程约束规则库

        Args:
            llm_response: LLM 原始响应文本
            contexts:     检索到的文档上下文切片列表

        Returns:
            CheckResult — passed=True 表示无阻断性违规
        """
        # 层 2：提取所有参数声称
        claimed_params = self._extract_claimed_params(llm_response)

        if not claimed_params:
            # 无可识别参数，直接通过（不误杀）
            return CheckResult(passed=True)

        logger.debug(f"[ConstraintChecker] 提取到参数声称: {claimed_params}")

        # 层 3：应用工程约束规则
        violations = []
        warnings = []

        for rule_fn in _CONSTRAINT_RULES:
            try:
                violation = rule_fn(claimed_params)
                if violation:
                    if violation.severity == "BLOCK":
                        violations.append(violation)
                        logger.warning(
                            f"[ConstraintChecker] 阻断性违规 [{violation.rule_id}]: "
                            f"{violation.description}"
                        )
                    else:
                        warnings.append(violation)
                        logger.info(
                            f"[ConstraintChecker] 警告 [{violation.rule_id}]: "
                            f"{violation.description}"
                        )
            except Exception as e:
                logger.debug(f"[ConstraintChecker] 规则 {rule_fn.__name__} 执行异常: {e}")

        passed = len(violations) == 0
        return CheckResult(passed=passed, violations=violations, warnings=warnings)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_claimed_params(self, text: str) -> Dict[str, float]:
        """
        从 LLM 响应文本中提取工程参数声称。
        返回 {参数类型: 数值} 字典。
        """
        from services.knowledge.parameter_registry import AEROSPACE_PARAM_TAXONOMY, _parse_number

        found: Dict[str, float] = {}
        param_names = "|".join(re.escape(k) for k in AEROSPACE_PARAM_TAXONOMY.keys())

        # 模式 1：参数名 + is/为/:/= + 数值
        pattern1 = re.compile(
            rf'({param_names})\s*(?:is|为|:|=|≈)\s*([\d,\.]+)',
            re.IGNORECASE
        )
        for m in pattern1.finditer(text):
            p_type = m.group(1).strip()
            val = _parse_number(m.group(2))
            if val is not None and p_type not in found:
                found[p_type] = val

        # 模式 2：数值 + 单位 + (参数名) 或 参数名 in 括号
        pattern2 = re.compile(
            rf'([\d,\.]+)\s*(?:kg|kt|lb|psi|kPa|g|kN)?\s*\(?\s*({param_names})\s*\)?',
            re.IGNORECASE
        )
        for m in pattern2.finditer(text):
            val = _parse_number(m.group(1))
            p_type = m.group(2).strip()
            if val is not None and p_type not in found:
                found[p_type] = val

        return found
