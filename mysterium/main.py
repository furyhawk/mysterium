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

from mysterium import __version__
from mysterium.config import Settings

app = FastAPI(
    title="Mysterium",
    description="RAG-powered research platform — upload documents, "
    "search with verity-rag, and synthesise reports with pydantic-deep agents",
    version=__version__,
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


@app.get("/api/version", include_in_schema=False)
async def get_version() -> dict[str, str]:
    """Return the current package version for the frontend and tooling."""
    return {"version": __version__}


from mysterium.routers import chat, documents, images, research  # noqa: E402

app.include_router(documents.router)
app.include_router(images.router)
app.include_router(research.router)
app.include_router(chat.router)


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
