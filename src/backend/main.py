from fastapi import FastAPI
from src.backend.api.routes import router

app = FastAPI(
    title="ContextAI API",
    description="Backend API service for ContextAI personal assistant",
    version="0.1.0",
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health_check():
    """Health check endpoint placeholder."""
    return {"status": "ok", "app": "ContextAI"}
