# ContextAI production image: FastAPI serves the API and the built React app.

# ---- 1. Build the frontend -------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime -------------------------------------------------------
FROM python:3.13-slim

# MALLOC_ARENA_MAX: glibc otherwise keeps a memory arena per thread, which adds up on a 512 MB instance
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    MALLOC_ARENA_MAX=2

WORKDIR /app

# Run as an unprivileged user
RUN useradd --create-home --uid 1000 app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app src/ ./src/
COPY --chown=app:app start.sh .
COPY --from=web --chown=app:app /web/dist ./frontend/dist
RUN mkdir -p /app/data/chroma && chown -R app:app /app/data && chmod +x /app/start.sh

USER app

# Bake the Chroma embedding model into the image so the first request after a restart isn't slow
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

EXPOSE 8000

CMD ["/bin/bash", "/app/start.sh"]
