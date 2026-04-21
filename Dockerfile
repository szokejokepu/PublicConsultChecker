# Stage 1: build React frontend
FROM node:22-slim AS frontend-builder
WORKDIR /build/rag-front
COPY rag-front/package.json rag-front/package-lock.json ./
RUN npm ci
COPY rag-front/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first — large (~300 MB), rarely changes, own cache layer.
# Must use the dedicated whl index; PyPI only carries CUDA builds.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Remaining deps. Strip the torch line so pip doesn't try to upgrade
# to the CUDA build from PyPI when resolving transformers[torch].
COPY requirements.txt .
RUN grep -v "^torch" requirements.txt | pip install --no-cache-dir -r /dev/stdin

# App source — explicit dirs keep the image lean (no trainer, tests, etc.)
COPY api/      ./api/
COPY pipeline/ ./pipeline/
COPY scraper/  ./scraper/
COPY notifier/ ./notifier/
COPY configs/  ./configs/
COPY main.py   ./

# Built frontend from stage 1
COPY --from=frontend-builder /build/rag-front/dist/ ./rag-front/dist/

ENV DB_PATH=/data/articles.db
ENV HF_HOME=/data/hf_cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/stats || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
