"""Mysterium main application — FastAPI entry point.

Serves:
- REST API proxying to verity-rag for document management & search
- REST API for AI-powered research report generation via pydantic-deep
- Static frontend for the browser UI
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from mysterium.config import Settings

app = FastAPI(
    title="Mysterium",
    description="RAG-powered research platform — upload documents, "
    "search with verity-rag, and synthesise reports with pydantic-deep agents",
    version="0.1.0",
)

# ── CORS ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ──────────────────────────────────────────────────────────

from mysterium.routers import documents, research  # noqa: E402

app.include_router(documents.router)
app.include_router(research.router)


# ── Static Frontend ─────────────────────────────────────────────────

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(static_dir), html=True),
        name="frontend",
    )

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/ui/")


# ── Launch Helper ───────────────────────────────────────────────────


def main() -> None:
    """Run the Mysterium server with uvicorn."""
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "mysterium.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=True,
    )


if __name__ == "__main__":
    main()
