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

# Minimal runtime utilities for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project files
COPY . .

# Cache model artifacts into the image during build so runtime stays offline.
ENV PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache \
    EMBEDDING_MODEL_NAME=BAAI/bge-large-zh-v1.5 \
    RERANKER_MODEL_NAME=BAAI/bge-reranker-base \
    MODEL_DOWNLOAD_STRICT=1

RUN mkdir -p "$HF_HOME"
RUN HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 EMBEDDING_LOCAL_FILES_ONLY=0 RERANKER_LOCAL_FILES_ONLY=0 \
    python scripts/pre_download_models.py

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    EMBEDDING_LOCAL_FILES_ONLY=1 \
    RERANKER_LOCAL_FILES_ONLY=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Start FastAPI via Uvicorn
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
