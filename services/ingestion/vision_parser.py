"""
VisionParser — V3.0 Gap B 多模态空间智能 (Task B-1)
=====================================================

将 PDF 中的表格和图像/图表从"跳过或平文本"升级为"结构化视觉理解"。

双引擎架构：
  1. 表格引擎 (TextTableEngine)：继承 V2.5 骨架，基于 PyMuPDF 结构化提取 + 文本对齐重建
  2. 视觉引擎 (VisionEngine)：Qwen2.5-VL-7B 本地推理，理解图表/复杂表格/图像语义

C1 合规：
  - Qwen2.5-VL-7B 通过 transformers 本地加载，运行时零外联
  - TRANSFORMERS_OFFLINE=1 强制离线模式
  - 模型权重在 Docker 构建时通过 pre_download_models.py 预烧录

降级策略：
  - VisionEngine 不可用（模型未加载）→ 自动回退到 TextTableEngine 文本描述
  - TextTableEngine 失败 → 返回原始文本，不崩溃
"""

import json
import logging
import os
import re
import base64
from typing import List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# C1: 强制离线模式
# ---------------------------------------------------------------------------
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")


# ---------------------------------------------------------------------------
# VisionEngine — Qwen2.5-VL-7B 本地推理
# ---------------------------------------------------------------------------

_VISION_ENGINE_INSTANCE = None
_VISION_ENGINE_LOAD_ATTEMPTED = False


def _get_vision_engine() -> Optional["VisionEngine"]:
    """懒加载单例，避免 import 时就加载 7B 模型阻塞服务启动。"""
    global _VISION_ENGINE_INSTANCE, _VISION_ENGINE_LOAD_ATTEMPTED
    if _VISION_ENGINE_LOAD_ATTEMPTED:
        return _VISION_ENGINE_INSTANCE
    _VISION_ENGINE_LOAD_ATTEMPTED = True
    try:
        _VISION_ENGINE_INSTANCE = VisionEngine()
        logger.info("[VisionParser] Qwen2.5-VL-7B 加载成功")
    except Exception as e:
        logger.warning(f"[VisionParser] Qwen2.5-VL-7B 不可用，将回退到文本模式: {e}")
        _VISION_ENGINE_INSTANCE = None
    return _VISION_ENGINE_INSTANCE


class VisionEngine:
    """
    Qwen2.5-VL-7B 本地视觉推理引擎。

    职责：
      - 接收 PNG bytes（由 PyMuPDF pixmap 生成）
      - 输出对图表/表格/图像的结构化中文描述（100-200字）

    模型路径约定：
      优先从 QWEN_VL_MODEL_PATH 环境变量读取（Docker 构建时设置）
      回退到 HuggingFace 缓存目录 Qwen/Qwen2.5-VL-7B-Instruct
    """

    MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
    DEFAULT_LOCAL_PATH = "models/Qwen2.5-VL-7B-Instruct"

    # 航空适航专用 System Prompt
    SYSTEM_PROMPT = """你是一个专业的航空适航文档图像分析助手。
请分析提供的图像，输出结构化的中文描述。

【要求】
1. 如果是表格：提取表头和关键数据行，格式为 JSON（最多 10 行）
2. 如果是图表/曲线图/示意图：描述其主题、坐标轴含义、关键数据点或趋势（100-200字）
3. 如果是流程图/框图：描述流程步骤和关键节点关系
4. 所有技术参数（单位、数值、条款号）必须原样保留，不得省略
5. 输出格式：{"type": "table"|"chart"|"diagram"|"figure", "description": "...", "data": {...}}
"""

    def __init__(self):
        model_path = os.environ.get("QWEN_VL_MODEL_PATH", self.DEFAULT_LOCAL_PATH)

        # 尝试本地路径优先，回退到 HuggingFace cache
        if not os.path.exists(model_path):
            model_path = self.MODEL_ID
            logger.info(f"[VisionEngine] 本地路径不存在，使用 HuggingFace ID: {model_path}")

        # 动态导入，避免没有 GPU/transformers 时整个模块无法导入
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
        import torch

        logger.info(f"[VisionEngine] 正在加载 {model_path}，这可能需要几分钟...")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32

        self.processor = AutoProcessor.from_pretrained(
            model_path,
            local_files_only=(os.environ.get("TRANSFORMERS_OFFLINE") == "1"),
        )
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=dtype,
            device_map="auto" if self.device == "cuda" else None,
            local_files_only=(os.environ.get("TRANSFORMERS_OFFLINE") == "1"),
        )
        if self.device == "cpu":
            self.model = self.model.to(self.device)

        logger.info(f"[VisionEngine] 模型加载完成，运行在 {self.device}")

    def analyze_image(self, image_bytes: bytes, hint: str = "") -> Optional[dict]:
        """
        对图像执行视觉推理，返回结构化字典。

        Args:
            image_bytes: PNG 格式的图像字节（由 PyMuPDF pixmap.tobytes("png") 生成）
            hint: 图像上下文提示（如"该图出现在关于燃油箱设计的章节"）

        Returns:
            {"type": str, "description": str, "data": dict} 或 None（推理失败时）
        """
        import torch

        try:
            # 将 PNG bytes 转为 base64 data URI
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_uri = f"data:image/png;base64,{b64}"

            user_content = f"请分析这张来自航空适航文档的图像。{('上下文提示: ' + hint) if hint else ''}"

            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_uri},
                        {"type": "text", "text": user_content},
                    ],
                },
            ]

            # Qwen2.5-VL 的 chat template 处理
            text_input = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.processor(
                text=[text_input],
                images=[image_uri],
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=512,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                )

            # 解码输出（去掉输入 tokens）
            input_len = inputs["input_ids"].shape[1]
            generated = output_ids[0][input_len:]
            raw_text = self.processor.decode(generated, skip_special_tokens=True).strip()

            # 尝试解析 JSON，降级为纯文本
            return _parse_vision_output(raw_text)

        except Exception as e:
            logger.error(f"[VisionEngine] 推理失败: {e}")
            return None


def _parse_vision_output(raw_text: str) -> dict:
    """
    从 LLM 输出中提取结构化 JSON，容错处理格式漂移。
    """
    raw_text = raw_text.strip()

    # 尝试直接解析 JSON
    try:
        result = json.loads(raw_text)
        if isinstance(result, dict) and "description" in result:
            return result
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 完全降级：包装为纯文本描述
    return {
        "type": "figure",
        "description": raw_text[:500],
        "data": {},
    }


# ---------------------------------------------------------------------------
# TextTableEngine — 文本表格重建（继承 V2.5，保持接口稳定）
# ---------------------------------------------------------------------------

class TextTableEngine:
    """
    基于 PyMuPDF 和文本对齐的表格重建引擎（V2.5 逻辑，接口不变）。
    """

    @staticmethod
    def parse_table(table_data: Any) -> str:
        """PyMuPDF table 对象 → JSON 字符串。"""
        try:
            raw_rows = table_data.extract()
            if not raw_rows or len(raw_rows) < 1:
                return ""
            header = [str(h or "").strip() for h in raw_rows[0]]
            structured = []
            for row in raw_rows[1:]:
                row_dict = {}
                for i in range(len(header)):
                    val = row[i] if i < len(row) else ""
                    row_dict[header[i]] = str(val or "").strip()
                structured.append(row_dict)
            return json.dumps(structured, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[TextTableEngine] parse_table 失败: {e}")
            return ""

    @staticmethod
    def parse_text_table(text_lines: List[str]) -> str:
        """
        文本对齐重建：从多空格分隔的行重建表格结构。
        """
        if len(text_lines) < 2:
            return ""

        rows_data = []
        for line in text_lines:
            tokens = re.split(r'\s{2,}', line.strip())
            if len(tokens) >= 2:
                rows_data.append(tokens)

        if len(rows_data) < 2:
            return ""

        headers = list(rows_data[0])
        max_cols = max(len(r) for r in rows_data)
        while len(headers) < max_cols:
            headers.append(f"Col_{len(headers) + 1}")

        structured = []
        for row in rows_data[1:]:
            entry = {}
            for i, val in enumerate(row):
                key = headers[i] if i < len(headers) else f"Col_{i + 1}"
                entry[key] = val
            structured.append(entry)

        return json.dumps(structured, indent=2, ensure_ascii=False) if structured else ""


# ---------------------------------------------------------------------------
# 公共 API — VisionParser（统一入口，保持向后兼容）
# ---------------------------------------------------------------------------

class VisionParser:
    """
    统一的视觉/表格解析入口。

    对调用方（parser.py）提供三个方法：
      - parse_table(table_data)         → 表格对象解析（PyMuPDF Table）
      - parse_text_table(text_lines)    → 文本行对齐重建
      - parse_image_block(image_bytes, bbox, page_context) → 视觉推理（Gap B 新增）
    """

    # 静态方法代理 TextTableEngine（保持向后兼容 parser.py 旧调用方式）
    @staticmethod
    def parse_table(table_data: Any) -> str:
        return TextTableEngine.parse_table(table_data)

    @staticmethod
    def parse_text_table(text_lines: List[str]) -> str:
        return TextTableEngine.parse_text_table(text_lines)

    @staticmethod
    def parse_image_block(
        image_bytes: bytes,
        bbox: Tuple[float, float, float, float],
        page_context: str = "",
        min_area: int = 5000,
    ) -> Optional[dict]:
        """
        对图像块执行视觉推理（Gap B 核心新增）。

        Args:
            image_bytes: PNG bytes（由 PyMuPDF page.get_pixmap(clip=bbox).tobytes("png")）
            bbox:        图像在页面中的坐标 (x0, y0, x1, y1)
            page_context: 该图像所在页面的文本摘要（供 LLM 理解上下文）
            min_area:    最小像素面积过滤，小于此值的图像视为装饰性元素，跳过

        Returns:
            {
              "type": "table"|"chart"|"diagram"|"figure",
              "description": str,     # 中文语义描述
              "data": dict,           # 结构化数据（表格行、图表数据点等）
              "bbox": list,           # 原始坐标
              "vision_model": str,    # "qwen2.5-vl" | "fallback-text"
            }
            或 None（图像太小/推理彻底失败）
        """
        if not image_bytes:
            return None

        # 面积过滤：跳过装饰性小图（logo、分隔线等）
        x0, y0, x1, y1 = bbox
        area = (x1 - x0) * (y1 - y0)
        if area < min_area:
            logger.debug(f"[VisionParser] 跳过小图像，面积={area:.0f} < {min_area}")
            return None

        # 尝试 Qwen2.5-VL 推理
        engine = _get_vision_engine()
        if engine is not None:
            result = engine.analyze_image(image_bytes, hint=page_context)
            if result:
                result["bbox"] = list(bbox)
                result["vision_model"] = "qwen2.5-vl"
                return result

        # 降级：返回图像位置的元数据描述（总比跳过好）
        logger.debug("[VisionParser] VisionEngine 不可用，生成降级描述")
        w = round(x1 - x0)
        h = round(y1 - y0)
        return {
            "type": "figure",
            "description": f"[图像元素，尺寸 {w}×{h}px，位于页面坐标 ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})。Qwen2.5-VL 模型未加载，无法进行语义解析。]",
            "data": {},
            "bbox": list(bbox),
            "vision_model": "fallback-text",
        }
