#!/usr/bin/env bash
set -e

# ContextAI Production Startup Script for Railway
# Supports running both FastAPI backend and Streamlit frontend in a single container,
# or running them as isolated services if APP_MODE is specified.

PORT="${PORT:-8501}"
BACKEND_PORT="${API_PORT:-8000}"
BACKEND_HOST="127.0.0.1"
APP_MODE="${APP_MODE:-all}"

echo "=========================================="
echo " Starting ContextAI"
echo " Mode:        ${APP_MODE}"
echo " Public Port: ${PORT}"
echo "=========================================="

# Mode 1: Backend only (for split service architectures)
if [ "$APP_MODE" = "backend" ]; then
    echo "Starting FastAPI backend on 0.0.0.0:${PORT}..."
    exec uvicorn src.backend.main:app --host 0.0.0.0 --port "${PORT}"
fi

# Mode 2: Frontend only (when connecting to a remote backend)
if [ "$APP_MODE" = "frontend" ]; then
    echo "Starting Streamlit frontend on 0.0.0.0:${PORT}..."
    exec streamlit run src/frontend/app.py \
        --server.port="${PORT}" \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --browser.gatherUsageStats=false
fi

# Mode 3: Unified Single-Container (Default for simple, zero-config Railway deployment)
# Graceful shutdown trap to ensure background FastAPI process is terminated on container stop
cleanup() {
    echo "Received termination signal. Shutting down ContextAI processes..."
    if [ -n "$BACKEND_PID" ]; then
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo "Starting FastAPI backend on ${BACKEND_HOST}:${BACKEND_PORT}..."
uvicorn src.backend.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# Wait for FastAPI backend to be ready
echo "Waiting for FastAPI health check to report OK..."
MAX_ATTEMPTS=40
ATTEMPT=0
READY=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if python3 -c "import urllib.request; resp = urllib.request.urlopen('http://${BACKEND_HOST}:${BACKEND_PORT}/health', timeout=1); exit(0 if resp.status == 200 else 1)" 2>/dev/null; then
        READY=1
        echo "FastAPI backend is healthy and responding!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 0.5
done

if [ $READY -ne 1 ]; then
    echo "Warning: FastAPI backend did not report healthy within expected time. Starting frontend anyway..."
fi

# Ensure Streamlit connects to the internal loopback backend if not explicitly overridden
export BACKEND_API_URL="${BACKEND_API_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
echo "Configured BACKEND_API_URL: ${BACKEND_API_URL}"

echo "Starting Streamlit frontend on 0.0.0.0:${PORT}..."
exec streamlit run src/frontend/app.py \
    --server.port="${PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
