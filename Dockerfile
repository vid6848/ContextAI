# ContextAI production image: FastAPI serves both the API and the web UI.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Run as an unprivileged user
RUN useradd --create-home --uid 1000 app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app src/ ./src/
COPY --chown=app:app start.sh .
RUN mkdir -p /app/data/chroma && chown -R app:app /app/data && chmod +x /app/start.sh

USER app

# Bake the Chroma embedding model into the image so the first request after a restart isn't slow
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

EXPOSE 8000

CMD ["/bin/bash", "/app/start.sh"]
