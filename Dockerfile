# Build Stage
FROM python:3.10-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final Stage (Air-gap Production)
FROM python:3.10-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project files
COPY . .

# Run Pre-download script to cache embeddings into the Docker image
# This strictly enforces C1 by eliminating runtime downloads.
RUN python scripts/pre_download_models.py

# Expose API port
EXPOSE 8000

# Set production env vars
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# C1 合规: 运行时强制离线，所有模型权重已在 build 阶段烧录
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1
ENV HF_HOME=/app/models

# Gap B: Qwen2.5-VL 本地路径（由 pre_download_models.py 写入）
ENV QWEN_VL_MODEL_PATH=/app/models/Qwen2.5-VL-7B-Instruct

# Start FastAPI via Uvicorn
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
