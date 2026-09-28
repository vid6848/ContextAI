#!/bin/bash

echo "Starting ContextAI on port ${PORT}..."

exec uvicorn src.backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT}"