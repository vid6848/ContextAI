# ContextAI Production Dockerfile
# Optimized for Railway single-container deployment

FROM python:3.11-slim

# Prevent Python from writing bytecode and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal OS dependencies for wheel compilation and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for caching layers
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source and assets
COPY src/ ./src/
COPY .streamlit/ ./.streamlit/
COPY start.sh .

# Ensure runtime directories exist and start script is executable
RUN mkdir -p /app/data/chroma && chmod +x /app/start.sh

# Default Streamlit port (Railway overrides this dynamically with $PORT)
EXPOSE 8501

# Start the unified application
CMD ["/bin/bash", "/app/start.sh"]
