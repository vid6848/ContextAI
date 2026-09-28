from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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


# ============================================================================
# Frontend (static web UI)
# Serves the new ContextAI chat interface from src/frontend/web.
# The API surface above is unchanged; this only adds static file hosting.
# ============================================================================
_WEB_DIR = Path(__file__).resolve().parents[1] / "frontend" / "web"

if _WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(_WEB_DIR / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    def serve_styles():
        return FileResponse(_WEB_DIR / "styles.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def serve_script():
        return FileResponse(_WEB_DIR / "app.js", media_type="application/javascript")
