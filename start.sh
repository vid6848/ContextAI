#!/bin/bash

echo "Starting ContextAI on port ${PORT:-8000}..."

exec uvicorn src.backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips="*"
