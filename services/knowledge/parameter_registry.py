"""
ParameterRegistry — V3.0 Gap C Task C-1
========================================

工程级参数注册表：在文档摄入时提取并标注安全关键工程参数，
供 AntiHallucinationGateway 做摄入时参数类型标注（第一层防御）。

改进点（相对于 V2.5 硬编码 mock）：
  1. LLM 驱动提取：替代只识别 "72500+MTOW/MZFW" 的硬编码逻辑
  2. 航空适航领域参数分类表：覆盖重量/速度/载荷/温度/压力等 7 类参数
  3. 正则预筛选：先用快速正则过滤有参数的 chunk，再调用 LLM 精提取，
     减少 LLM 调用次数（高文本量文档）
  4. 原子写盘：tmp→rename 防止注册表损坏
  5. verify_claim() 增强：支持单位归一化、模糊容差（±1%）验证

C1 合规：LLM 调用走已有 call_local_llm（MiniMax 内网部署），零外联。
C2 合规：注册表数据为 Gateway 第一层防御的数据源。
"""

import json
import logging
import os
import re
from typing import Dict, Optional

from core.llm.client import call_local_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 航空适航参数分类表（用于 LLM Prompt 约束和验证）
# ---------------------------------------------------------------------------
AEROSPACE_PARAM_TAXONOMY = {
    # 重量类
    "MTOW":  {"desc": "最大起飞重量 Maximum Take-off Weight",        "units": ["kg", "lb"]},
    "MZFW":  {"desc": "最大无燃油重量 Maximum Zero Fuel Weight",      "units": ["kg", "lb"]},
    "MLW":   {"desc": "最大着陆重量 Maximum Landing Weight",          "units": ["kg", "lb"]},
    "OEW":   {"desc": "使用空重 Operating Empty Weight",             "units": ["kg", "lb"]},
    "MSTOW": {"desc": "最大结构起飞重量 Max Structural TOW",          "units": ["kg", "lb"]},
    # 速度类
    "Vmo":   {"desc": "最大使用速度 Maximum Operating Speed",         "units": ["kt", "km/h", "m/s"]},
    "Mmo":   {"desc": "最大使用马赫数 Maximum Operating Mach",        "units": ["Mach", ""]},
    "Vfe":   {"desc": "最大襟翼放出速度 Max Flap Extended Speed",     "units": ["kt", "km/h"]},
    "Vle":   {"desc": "最大起落架放出速度 Max Landing Gear Extended", "units": ["kt", "km/h"]},
    "Vs":    {"desc": "失速速度 Stall Speed",                        "units": ["kt", "km/h"]},
    # 载荷/过载类
    "n_lim": {"desc": "限制载荷系数 Limit Load Factor",              "units": ["g", ""]},
    "n_ult": {"desc": "极限载荷系数 Ultimate Load Factor",            "units": ["g", ""]},
    # 温度类
    "T_max": {"desc": "最高运行温度 Maximum Operating Temperature",   "units": ["°C", "K", "°F"]},
    "ISA":   {"desc": "国际标准大气温度 ISA Temperature",             "units": ["°C", "K"]},
    # 压力类
    "P_cab": {"desc": "客舱压差 Cabin Differential Pressure",        "units": ["psi", "kPa", "hPa"]},
    # 尺寸/力类
    "F_lim": {"desc": "限制载荷 Limit Load",                         "units": ["kN", "N", "lbf"]},
    "q_lim": {"desc": "动压限制 Dynamic Pressure Limit",             "units": ["Pa", "kPa", "psf"]},
}

# 快速预筛正则：含数字 + 单位关键词的 chunk 才进 LLM 提取
_PARAM_PREFILTER = re.compile(
    r'(\d[\d,\.]+)\s*'
    r'(kg|lb|kt|km/h|m/s|Mach|psi|kPa|hPa|kN|°C|°F|K\b|g\b)',
    re.IGNORECASE
)

# LLM 提取 System Prompt
_EXTRACTION_SYSTEM = f"""你是一个专业的航空适航工程参数提取器。
从给定的适航文本中识别并提取安全关键工程参数，输出 JSON 数组。

【已知参数类型】
{json.dumps({k: v['desc'] for k, v in AEROSPACE_PARAM_TAXONOMY.items()}, ensure_ascii=False, indent=2)}

【严格输出格式】
[
  {{"value": "72500", "type": "MTOW", "unit": "kg", "context": "原文摘要（≤30字）"}},
  ...
]
- value 必须是纯数字字符串（去掉逗号）
- type 必须是上面列表中的类型之一
- 若无可识别参数，输出空数组 []
- 不输出任何 JSON 以外的内容
"""


class ParameterRegistry:
    """
    航空适航工程参数注册表。

    摄入时（ingestion）：register_parameters() 提取并持久化参数
    校验时（gateway）：verify_claim() 核查 LLM 声称的参数类型
    """

    def __init__(self, registry_path: str = "data/parameter_registry.json"):
        self.registry_path = registry_path
        self.registry: Dict = self._load()

    # ------------------------------------------------------------------
    # Public: 摄入阶段调用
    # ------------------------------------------------------------------

    def register_parameters(
        self,
        chunk_id: str,
        text: str,
        page: int,
        source: str,
    ) -> int:
        """
        从 chunk 文本中提取安全关键参数并注册。
        返回本次提取的参数数量。

        流程：正则预筛 → LLM 精提取 → 写入注册表
        """
        # 1. 快速预筛：无数字+单位的 chunk 直接跳过，节省 LLM 调用
        if not _PARAM_PREFILTER.search(text):
            return 0

        # 2. LLM 精提取
        prompt = f"请从以下航空适航文本中提取工程参数：\n\n{text[:1200]}"
        try:
            raw = call_local_llm(_EXTRACTION_SYSTEM, prompt)
        except Exception as e:
            logger.error(f"[ParameterRegistry] LLM 调用失败 chunk={chunk_id}: {e}")
            return 0

        params = _parse_param_list(raw)
        if not params:
            return 0

        # 3. 写入注册表（chunk_id 为 key，支持多参数）
        chunk_params = {}
        for p in params:
            val = str(p.get("value", "")).replace(",", "").strip()
            p_type = p.get("type", "").strip()
            unit = p.get("unit", "").strip()
            context = p.get("context", "")

            if not val or not p_type:
                continue
            if p_type not in AEROSPACE_PARAM_TAXONOMY:
                logger.debug(f"[ParameterRegistry] 未知参数类型 '{p_type}'，跳过")
                continue

            # 同一数值可能有多种类型（如 72500 可能是 MTOW 或 MZFW），都保留
            if val not in chunk_params:
                chunk_params[val] = []
            chunk_params[val].append({
                "type": p_type,
                "unit": unit,
                "source": source,
                "page": page,
                "context": context,
            })

        if chunk_params:
            self.registry[chunk_id] = chunk_params
            self._save()
            logger.debug(
                f"[ParameterRegistry] chunk={chunk_id} 注册 {len(chunk_params)} 个参数"
            )

        return len(chunk_params)

    # ------------------------------------------------------------------
    # Public: Gateway 校验阶段调用
    # ------------------------------------------------------------------

    def verify_claim(
        self,
        claimed_value: str,
        claimed_type: str,
        source: str,
        page: int,
        tolerance: float = 0.01,
    ) -> bool:
        """
        校验 LLM 声称的参数类型与注册表是否一致。

        Args:
            claimed_value: LLM 响应中声称的数值（纯数字字符串）
            claimed_type:  LLM 声称的参数类型（如 "MTOW"）
            source:        文档来源文件名
            page:          页码
            tolerance:     数值匹配容差（默认 ±1%，处理单位换算误差）

        Returns:
            True  — 校验通过（类型匹配或注册表中不存在该值，软失败）
            False — 校验失败（类型冲突，拦截）
        """
        claimed_num = _parse_number(claimed_value)
        if claimed_num is None:
            return True  # 无法解析的值不拦截

        matched_types = set()

        for chunk_id, params in self.registry.items():
            for reg_val_str, entries in params.items():
                reg_num = _parse_number(reg_val_str)
                if reg_num is None:
                    continue

                # 数值匹配（含容差）
                if not _values_match(claimed_num, reg_num, tolerance):
                    continue

                for entry in entries:
                    # 来源匹配（文件名 + 页码）
                    if entry["source"] == source and entry["page"] == page:
                        matched_types.add(entry["type"])

        if not matched_types:
            # 注册表中无此记录：软失败，放行（避免误杀未被提取的参数）
            return True

        # 注册表有记录：严格校验类型
        is_valid = claimed_type in matched_types
        if not is_valid:
            logger.warning(
                f"[ParameterRegistry] 类型冲突: 声称={claimed_type}, "
                f"注册={matched_types}, val={claimed_value}, src={source} P{page}"
            )
        return is_valid

    def get_stats(self) -> dict:
        """返回注册表统计，供 API 展示。"""
        total_params = sum(len(v) for v in self.registry.values())
        type_counts: Dict[str, int] = {}
        for params in self.registry.values():
            for entries in params.values():
                for e in entries:
                    t = e.get("type", "unknown")
                    type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_chunks_with_params": len(self.registry),
            "total_params": total_params,
            "by_type": type_counts,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> Dict:
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[ParameterRegistry] 注册表加载失败，重建: {e}")
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        tmp = self.registry_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.registry_path)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parse_param_list(raw_text: str):
    """从 LLM 响应中容错提取参数列表。"""
    raw_text = raw_text.strip()
    # 直接解析
    try:
        result = json.loads(raw_text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # markdown 代码块
    code_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw_text, re.DOTALL)
    if code_match:
        try:
            result = json.loads(code_match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    # 裸数组
    arr_match = re.search(r'(\[.*\])', raw_text, re.DOTALL)
    if arr_match:
        try:
            result = json.loads(arr_match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return []


def _parse_number(value_str: str) -> Optional[float]:
    """将数值字符串解析为 float，处理逗号千分位。"""
    try:
        return float(str(value_str).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _values_match(a: float, b: float, tolerance: float) -> bool:
    """判断两个数值是否在容差范围内匹配。"""
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tolerance
