from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.backend.api.routes import router

# Built React app (npm run build in frontend/). Docker copies it to the same relative location.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

app = FastAPI(
    title="ContextAI API",
    description="Backend API service for ContextAI personal assistant",
    version="0.2.0",
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health_check():
    """Liveness probe used by the hosting platform."""
    return {"status": "ok", "app": "ContextAI"}


def mount_frontend(application: FastAPI, dist: Path) -> None:
    """Serve the single-page app: hashed assets from /assets, real files from dist, and index.html for
    every other non-API path so client-side routes like /c/<id> survive a reload."""
    if not (dist / "index.html").is_file():
        @application.get("/", include_in_schema=False)
        def frontend_not_built():
            return JSONResponse(
                status_code=503,
                content={"detail": "Frontend not built. Run `npm run build` in frontend/, or use `npm run dev`."},
            )
        return

    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    root = dist.resolve()

    @application.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "assets/")) or path in {"api", "health"}:
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})


mount_frontend(app, FRONTEND_DIST)
