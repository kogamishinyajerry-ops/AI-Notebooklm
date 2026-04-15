"""
pre_download_models.py — Docker 构建阶段模型预烧录脚本
======================================================

在 Docker build 时执行（RUN python scripts/pre_download_models.py），
将所有模型权重固化到镜像内，确保运行时零外联（C1 合规）。

模型清单：
  1. BAAI/bge-large-zh-v1.5       — 文本向量化嵌入模型（V2.5 原有）
  2. BAAI/bge-reranker-large       — 跨编码器重排序模型（V2.5 原有）
  3. Qwen/Qwen2.5-VL-7B-Instruct  — 多模态视觉语言模型（V3.0 Gap B 新增）

C1 合规说明：
  - 所有下载操作仅在 Docker BUILD 阶段发生，运行时设置 TRANSFORMERS_OFFLINE=1
  - 模型缓存到 /app/models/（通过 HF_HOME 环境变量控制）
  - Qwen2.5-VL 使用 torch_dtype=float16 减少显存占用（约 14GB）
"""

import os
import sys

# 构建阶段允许联网，运行时不允许
# 此脚本在 Docker build 时执行，不受 TRANSFORMERS_OFFLINE 约束
print("=" * 60)
print("COMAC NotebookLM — 模型预烧录脚本 (Docker Build Phase)")
print("=" * 60)

# 模型缓存目录（与 Dockerfile ENV HF_HOME 保持一致）
MODEL_CACHE_DIR = os.environ.get("HF_HOME", "/app/models")
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
print(f"模型缓存目录: {MODEL_CACHE_DIR}\n")

# ------------------------------------------------------------------
# 1. BGE 嵌入模型（V2.5 原有）
# ------------------------------------------------------------------
print(">>> [1/3] 下载 BAAI/bge-large-zh-v1.5 (嵌入模型)...")
try:
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("BAAI/bge-large-zh-v1.5", cache_folder=MODEL_CACHE_DIR)
    print("    ✓ bge-large-zh-v1.5 缓存完成\n")
except Exception as e:
    print(f"    ✗ bge-large-zh-v1.5 下载失败: {e}")
    print("    警告: 嵌入功能将不可用\n")

# ------------------------------------------------------------------
# 2. BGE Reranker（V2.5 原有）
# ------------------------------------------------------------------
print(">>> [2/3] 下载 BAAI/bge-reranker-large (重排序模型)...")
try:
    from sentence_transformers import CrossEncoder
    CrossEncoder("BAAI/bge-reranker-large", max_length=512)
    print("    ✓ bge-reranker-large 缓存完成\n")
except Exception as e:
    print(f"    ✗ bge-reranker-large 下载失败 (非致命): {e}\n")

# ------------------------------------------------------------------
# 3. Qwen2.5-VL-7B-Instruct（V3.0 Gap B 新增）
# ------------------------------------------------------------------
print(">>> [3/3] 下载 Qwen/Qwen2.5-VL-7B-Instruct (多模态视觉模型)...")
print("    注意: 模型约 15GB，下载可能需要较长时间...")

QWEN_VL_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
QWEN_VL_LOCAL_PATH = os.path.join(MODEL_CACHE_DIR, "Qwen2.5-VL-7B-Instruct")

try:
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    import torch

    dtype = torch.float16  # 半精度，显存约 14GB；CPU 环境自动降为 float32

    print(f"    正在下载处理器...")
    processor = AutoProcessor.from_pretrained(
        QWEN_VL_MODEL_ID,
        cache_dir=MODEL_CACHE_DIR,
    )
    processor.save_pretrained(QWEN_VL_LOCAL_PATH)
    print(f"    处理器已保存至: {QWEN_VL_LOCAL_PATH}")

    print(f"    正在下载模型权重（float16）...")
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        QWEN_VL_MODEL_ID,
        torch_dtype=dtype,
        cache_dir=MODEL_CACHE_DIR,
        # 构建阶段不使用 device_map="auto"，避免构建机无 GPU 时报错
        device_map=None,
        low_cpu_mem_usage=True,
    )
    model.save_pretrained(QWEN_VL_LOCAL_PATH)
    print(f"    模型权重已保存至: {QWEN_VL_LOCAL_PATH}")
    print("    ✓ Qwen2.5-VL-7B-Instruct 缓存完成\n")

    # 写入本地路径环境变量提示（供 Dockerfile ENV 引用）
    env_hint_path = os.path.join(MODEL_CACHE_DIR, "qwen_vl_model_path.txt")
    with open(env_hint_path, "w") as f:
        f.write(QWEN_VL_LOCAL_PATH)
    print(f"    本地路径记录于: {env_hint_path}")

except ImportError as e:
    print(f"    ✗ transformers 未安装或版本不支持 Qwen2.5-VL: {e}")
    print("    解决方案: pip install transformers>=4.45.0 qwen-vl-utils")
    print("    警告: 视觉解析功能将降级为文本模式运行\n")
except Exception as e:
    print(f"    ✗ Qwen2.5-VL-7B 下载失败: {e}")
    print("    警告: 视觉解析功能将降级为文本模式运行\n")

# ------------------------------------------------------------------
# 完成汇报
# ------------------------------------------------------------------
print("=" * 60)
print("模型预烧录完成。运行时请确保以下环境变量已设置：")
print(f"  TRANSFORMERS_OFFLINE=1")
print(f"  HF_HOME={MODEL_CACHE_DIR}")
print(f"  QWEN_VL_MODEL_PATH={QWEN_VL_LOCAL_PATH}")
print("=" * 60)
