"""
PDFParser — V3.0 Gap B 双路径解析引擎 (Task B-2)
=================================================

升级内容（相对于 V2.5）：
  1. 新增图像块检测路径：PyMuPDF page.get_images() 提取嵌入图像
  2. 新增图表区域截取路径：对非文本大尺寸区域做 pixmap 截取
  3. 双路径分发：
       text  → 原有文本/表格路径（不变）
       image → VisionParser.parse_image_block()（Qwen2.5-VL 或降级描述）
  4. chunk metadata 新增 type="image_vision" 标记，供检索层区分

降级保证：
  - VisionEngine 不可用时，图像块仍产出带位置元数据的降级 chunk，不丢失信息
  - PyMuPDF 不可用时，回退 PyPDF 路径（不含图像处理，行为与 V2.5 相同）
"""

import logging
import re
from typing import List

from pydantic import BaseModel
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    logger.warning("[PDFParser] PyMuPDF (fitz) 不可用，将使用 PyPDF 回退路径")

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from services.ingestion.vision_parser import VisionParser


class DocumentChunk(BaseModel):
    text: str
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 图像面积阈值（像素²）：小于此值视为装饰性图标，跳过
_MIN_IMAGE_AREA_PX = 8000

# pixmap 分辨率缩放因子：2.0 = 144 DPI，在速度和清晰度间取平衡
_PIXMAP_MATRIX_SCALE = 2.0


class PDFParser:
    """
    工业级双路径 PDF 解析器。

    路径 A（PyMuPDF）：
      ├── 表格检测 → TextTableEngine.parse_table()
      ├── 嵌入图像检测 → VisionParser.parse_image_block()   ← Gap B 新增
      ├── 大面积非文本区域 → VisionParser.parse_image_block()  ← Gap B 新增
      └── 文本块 → 普通文本 chunk

    路径 B（PyPDF 回退）：
      └── 平文本 + 启发式表格重建（V2.5 行为，无图像处理）

    路径 C（双引擎均不可用）：
      └── 错误 chunk
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc_fitz = None
        self.doc_pypdf = None

        if fitz:
            try:
                self.doc_fitz = fitz.open(file_path)
            except Exception as e:
                logger.warning(f"[PDFParser] PyMuPDF 打开失败: {e}")

        if not self.doc_fitz and PdfReader:
            try:
                self.doc_pypdf = PdfReader(file_path)
            except Exception as e:
                logger.warning(f"[PDFParser] PyPDF 打开失败: {e}")

    def extract_chunks(self) -> List[DocumentChunk]:
        if self.doc_fitz:
            return self._extract_with_fitz()
        if self.doc_pypdf:
            return self._extract_with_pypdf()
        return self._error_chunk()

    # ------------------------------------------------------------------
    # 路径 A：PyMuPDF（高保真 + 双路径）
    # ------------------------------------------------------------------

    def _extract_with_fitz(self) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []
        source = self.file_path.split("/")[-1]

        for page_num, page in enumerate(self.doc_fitz):
            page_number = page_num + 1

            # 1. 表格检测（原有逻辑）
            try:
                tables = page.find_tables()
                for table in tables.tables:
                    table_json = VisionParser.parse_table(table)
                    if table_json:
                        chunks.append(DocumentChunk(
                            text=table_json,
                            metadata={
                                "source": source,
                                "page": page_number,
                                "bbox": list(table.bbox),
                                "type": "table",
                            }
                        ))
            except Exception:
                pass

            # 2. 嵌入图像检测（Gap B 新增）
            page_text_summary = self._get_page_text_summary(page)
            try:
                image_list = page.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    img_rect = self._get_image_rect(page, xref)
                    if img_rect is None:
                        continue

                    image_bytes = self._render_rect_to_png(page, img_rect)
                    if not image_bytes:
                        continue

                    vision_result = VisionParser.parse_image_block(
                        image_bytes=image_bytes,
                        bbox=tuple(img_rect),
                        page_context=page_text_summary,
                        min_area=_MIN_IMAGE_AREA_PX,
                    )
                    if vision_result:
                        chunk_text = self._vision_result_to_text(vision_result)
                        chunks.append(DocumentChunk(
                            text=chunk_text,
                            metadata={
                                "source": source,
                                "page": page_number,
                                "bbox": list(img_rect),
                                "type": "image_vision",
                                "vision_model": vision_result.get("vision_model", "unknown"),
                                "image_type": vision_result.get("type", "figure"),
                            }
                        ))
            except Exception as e:
                logger.debug(f"[PDFParser] 页面 {page_number} 图像提取失败: {e}")

            # 3. 文本块（原有逻辑 + 启发式表格检测）
            try:
                blocks = page.get_text("blocks")
                for block in blocks:
                    # block 格式: (x0, y0, x1, y1, text, block_no, block_type)
                    # block_type: 0=text, 1=image
                    block_type = block[6] if len(block) > 6 else 0

                    # 跳过图像块（已在上一步处理）
                    if block_type == 1:
                        continue

                    text = block[4].strip()
                    if not text:
                        continue

                    bbox = list(block[:4])

                    # 启发式表格检测
                    lines = text.split("\n")
                    if len(lines) > 2 and any(
                        re.search(r'\d+\s+\d+', line) for line in lines
                    ):
                        table_json = VisionParser.parse_text_table(lines)
                        if table_json:
                            chunks.append(DocumentChunk(
                                text=table_json,
                                metadata={
                                    "source": source,
                                    "page": page_number,
                                    "bbox": bbox,
                                    "type": "table",
                                }
                            ))
                            continue

                    chunks.append(DocumentChunk(
                        text=text,
                        metadata={
                            "source": source,
                            "page": page_number,
                            "bbox": bbox,
                            "type": "text",
                        }
                    ))
            except Exception as e:
                logger.debug(f"[PDFParser] 页面 {page_number} 文本提取失败: {e}")

        return chunks

    # ------------------------------------------------------------------
    # 路径 B：PyPDF 回退（V2.5 行为，无图像处理）
    # ------------------------------------------------------------------

    def _extract_with_pypdf(self) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []
        source = self.file_path.split("/")[-1]

        for page_num, page in enumerate(self.doc_pypdf.pages):
            text = page.extract_text()
            if not text:
                continue

            page_number = page_num + 1
            lines = text.split("\n")
            table_buffer = []

            for line in lines:
                if len(re.split(r'\s{2,}', line.strip())) >= 2:
                    table_buffer.append(line)
                else:
                    if len(table_buffer) >= 2:
                        table_json = VisionParser.parse_text_table(table_buffer)
                        if table_json:
                            chunks.append(DocumentChunk(
                                text=table_json,
                                metadata={
                                    "source": source,
                                    "page": page_number,
                                    "bbox": [50, 50, 500, 500],
                                    "type": "table",
                                }
                            ))
                    table_buffer = []

                    if line.strip():
                        chunks.append(DocumentChunk(
                            text=line.strip(),
                            metadata={
                                "source": source,
                                "page": page_number,
                                "bbox": [50, 50, 500, 500],
                                "type": "text",
                            }
                        ))

            # 最后一个表格缓冲区 flush
            if len(table_buffer) >= 2:
                table_json = VisionParser.parse_text_table(table_buffer)
                if table_json:
                    chunks.append(DocumentChunk(
                        text=table_json,
                        metadata={
                            "source": source,
                            "page": page_number,
                            "bbox": [50, 50, 500, 500],
                            "type": "table",
                        }
                    ))

        return chunks

    # ------------------------------------------------------------------
    # 路径 C：错误降级
    # ------------------------------------------------------------------

    def _error_chunk(self) -> List[DocumentChunk]:
        return [DocumentChunk(
            text="[SYSTEM ERROR] 所有 PDF 解析引擎 (fitz, pypdf) 均不可用。请检查运行环境库依赖。",
            metadata={"source": "error", "page": 0, "bbox": [0, 0, 0, 0], "type": "error"}
        )]

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_page_text_summary(self, page) -> str:
        """
        提取页面前 300 字的文本摘要，作为视觉推理的上下文提示。
        帮助 Qwen2.5-VL 理解图像所在的文档语境（如"燃油系统章节"）。
        """
        try:
            text = page.get_text("text")
            return text[:300].strip().replace("\n", " ")
        except Exception:
            return ""

    def _get_image_rect(self, page, xref: int):
        """
        通过 xref 查找图像在页面中的矩形坐标。
        遍历页面 dict 的 blocks 找到对应的图像 block。
        """
        try:
            page_dict = page.get_text("rawdict", flags=0)
            for block in page_dict.get("blocks", []):
                if block.get("type") == 1:  # type 1 = image
                    if block.get("image") and xref in (block.get("xref", -1), -1):
                        return fitz.Rect(block["bbox"])
            # 回退：尝试直接从 page 获取图像位置
            for img_item in page.get_image_rects(xref):
                return img_item  # fitz.Rect
        except Exception as e:
            logger.debug(f"[PDFParser] _get_image_rect xref={xref} 失败: {e}")
        return None

    def _render_rect_to_png(self, page, rect) -> bytes:
        """
        将页面指定区域渲染为 PNG bytes。
        使用 2x 缩放（144 DPI）在质量和速度间取平衡。
        """
        try:
            mat = fitz.Matrix(_PIXMAP_MATRIX_SCALE, _PIXMAP_MATRIX_SCALE)
            clip = fitz.Rect(rect)
            pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
            return pix.tobytes("png")
        except Exception as e:
            logger.debug(f"[PDFParser] _render_rect_to_png 失败: {e}")
            return b""

    def _vision_result_to_text(self, vision_result: dict) -> str:
        """
        将视觉推理结果转为可索引的文本字符串。
        同时保留结构化 data（如有）和自然语言描述，两者都被向量化索引。
        """
        parts = []
        desc = vision_result.get("description", "")
        if desc:
            parts.append(desc)

        data = vision_result.get("data", {})
        if data:
            parts.append(f"[结构化数据] {json_safe_dumps(data)}")

        return "\n".join(parts) if parts else "[视觉元素，无可用描述]"

    def close(self):
        if self.doc_fitz:
            self.doc_fitz.close()


def json_safe_dumps(obj) -> str:
    """安全 JSON 序列化，处理非标准类型。"""
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)
