"""History router — list, retrieve, export and delete persisted artifacts.

Serves the filesystem-backed history written by :mod:`mysterium.history`:

- ``GET /api/history/reports``                 — saved research reports
- ``GET /api/history/reports/{id}``            — full report JSON
- ``GET /api/history/reports/{id}/export``     — download as md/json/html
- ``DELETE /api/history/reports/{id}``         — remove a report
- the same four endpoints under ``/api/history/chats`` for conversations.

When ``HISTORY_ENABLED=false`` the store returns empty lists and ``None`` for
loads, so the list endpoints come back empty and get/export/delete return 404.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from mysterium.config import Settings, get_settings
from mysterium.history import (
    HistoryStore,
    conversation_to_markdown,
    markdown_to_html,
    report_to_markdown,
)

router = APIRouter(prefix="/api/history", tags=["history"])

_EXPORT_FORMATS = {"md", "json", "html"}


async def get_store(settings: Settings = Depends(get_settings)) -> HistoryStore:
    """Dependency providing a filesystem history store."""
    return HistoryStore(root=settings.data_dir, enabled=settings.history_enabled)


def _render_export(
    *,
    artifact_id: str,
    fmt: str,
    title: str,
    markdown: str,
    raw: dict,
) -> tuple[str, str, str]:
    """Return ``(filename, media_type, content)`` for an export download."""
    fmt = (fmt or "md").lower()
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{fmt}' (use md, json or html)",
        )
    if fmt == "json":
        return (
            f"{artifact_id}.json",
            "application/json",
            json.dumps(raw, ensure_ascii=False, indent=2),
        )
    if fmt == "html":
        return f"{artifact_id}.html", "text/html", markdown_to_html(markdown, title=title)
    return f"{artifact_id}.md", "text/markdown; charset=utf-8", markdown


def _download_response(filename: str, media_type: str, content: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


# ── Reports ────────────────────────────────────────────────────────


@router.get("/reports")
async def list_reports(store: HistoryStore = Depends(get_store)):
    """Summaries of all saved research reports, newest first."""
    return {"items": store.list_reports()}


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    store: HistoryStore = Depends(get_store),
):
    """The full stored research report as JSON."""
    report = store.load_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = "md",
    store: HistoryStore = Depends(get_store),
):
    """Download a saved report as Markdown, JSON or a standalone HTML page."""
    report = store.load_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    filename, media_type, content = _render_export(
        artifact_id=report_id,
        fmt=format,
        title=report.get("title") or "research-report",
        markdown=report_to_markdown(report),
        raw=report,
    )
    return _download_response(filename, media_type, content)


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    store: HistoryStore = Depends(get_store),
):
    """Delete a saved research report."""
    if not store.delete_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "deleted"}


# ── Chats ──────────────────────────────────────────────────────────


@router.get("/chats")
async def list_chats(store: HistoryStore = Depends(get_store)):
    """Summaries of all saved conversations, most recent first."""
    return {"items": store.list_chats()}


@router.get("/chats/{conversation_id}")
async def get_chat(
    conversation_id: str,
    store: HistoryStore = Depends(get_store),
):
    """The full stored chat transcript as JSON."""
    chat = store.load_chat(conversation_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return chat


@router.get("/chats/{conversation_id}/export")
async def export_chat(
    conversation_id: str,
    format: str = "md",
    store: HistoryStore = Depends(get_store),
):
    """Download a saved conversation as Markdown, JSON or an HTML page."""
    chat = store.load_chat(conversation_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    filename, media_type, content = _render_export(
        artifact_id=conversation_id,
        fmt=format,
        title=chat.get("title") or "conversation",
        markdown=conversation_to_markdown(chat),
        raw=chat,
    )
    return _download_response(filename, media_type, content)


@router.delete("/chats/{conversation_id}")
async def delete_chat(
    conversation_id: str,
    store: HistoryStore = Depends(get_store),
):
    """Delete a saved conversation."""
    if not store.delete_chat(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}
