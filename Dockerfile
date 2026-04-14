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

# Start FastAPI via Uvicorn
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
