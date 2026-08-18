"""Research and report generation router.

Uses pydantic-deep agents to synthesise structured research reports
from RAG-retrieved documents and LLM analysis.

- ``POST /api/research/report``        — full report, returned when done.
- ``POST /api/research/report/stream`` — same report as Server-Sent Events,
  with live progress phases before the final ``report`` event.
- ``POST /api/research/ask``           — quick Q&A answered from RAG context.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from mysterium.agents import generate_research_report
from mysterium.agents import stream_research_report as stream_report_generation
from mysterium.clients.rag_client import RAGClient
from mysterium.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


async def get_rag_client(settings: Settings = Depends(get_settings)) -> RAGClient:
    """Dependency providing a connected RAG client."""
    return RAGClient(base_url=settings.rag_server_url)


class ReportRequest(BaseModel):
    """Parameters for research report generation."""

    query: str = Field(..., min_length=1)
    collection_name: str = "documents"
    limit: int = Field(default=10, ge=1, le=50)
    model: str = "claude-sonnet-4-20250514"
    use_web: bool | None = Field(
        default=None,
        description=(
            "Augment RAG findings with web search. "
            "Defaults to the server RESEARCH_USE_WEB setting."
        ),
    )
    use_web_fetch: bool | None = Field(
        default=None,
        description=(
            "Fetch full web pages to augment RAG findings. "
            "Defaults to the server RESEARCH_WEB_FETCH setting."
        ),
    )
    use_web_fetch_local: bool | None = Field(
        default=None,
        description=(
            "Fetch pages with a local markdownify-based tool instead of "
            "Anthropic's server-side web-fetch tool. Works with every "
            "Anthropic-compatible gateway. Defaults to the server "
            "RESEARCH_WEB_FETCH_LOCAL setting."
        ),
    )


class AskRequest(BaseModel):
    """Parameters for quick Q&A."""

    question: str = Field(..., min_length=1)
    collection_name: str = "documents"
    limit: int = Field(default=5, ge=1, le=50)


def _resolve_web_settings(
    settings: Settings, body: ReportRequest
) -> tuple[bool, bool, bool]:
    """Resolve web search/fetch toggles from request > env settings.

    Returns ``(use_web, web_fetch, web_fetch_local)`` — the effective values
    shared by the blocking and the streaming report endpoints.
    """
    use_web = settings.research_use_web if body.use_web is None else body.use_web

    # web_fetch_local: request > RESEARCH_WEB_FETCH_LOCAL setting > True.
    if body.use_web_fetch_local is not None:
        web_fetch_local = body.use_web_fetch_local
    else:
        web_fetch_local = settings.research_web_fetch_local

    # The server-side web-fetch tool is rejected by most Anthropic-
    # compatible gateways (it is not part of the standard tool set they
    # deserialise). Explicitly configured RESEARCH_WEB_FETCH wins; otherwise
    # auto: fetch stays on for the official Anthropic API (no custom base
    # URL), AND for custom gateways whenever the local fetch tool is in use
    # — the local markdownify tool works with every gateway. Fetch is only
    # auto-disabled for gateways when falling back to the server-side tool.
    if body.use_web_fetch is not None:
        web_fetch = body.use_web_fetch
    elif settings.research_web_fetch is not None:
        web_fetch = settings.research_web_fetch
    else:
        web_fetch = web_fetch_local or not bool(settings.anthropic_base_url)

    return use_web, web_fetch, web_fetch_local


def _sse(event: dict) -> str:
    """Encode a single JSON object as a Server-Sent Event."""
    return f"data: {json.dumps(event)}\n\n"


@router.post("/report")
async def create_research_report(
    body: ReportRequest,
    settings: Settings = Depends(get_settings),
    rag: RAGClient = Depends(get_rag_client),
):
    """Generate a structured research report on a topic.

    The agent:
    1. Searches the RAG document store for relevant content
    2. Synthesises findings into a structured report with citations
    3. Returns the report as a structured JSON object
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "ANTHROPIC_API_KEY not configured. "
                "Set it in your .env file to use the research agent."
            ),
        )

    use_web, web_fetch, web_fetch_local = _resolve_web_settings(settings, body)
    try:
        report = await generate_research_report(
            rag_client=rag,
            query=body.query,
            collection_name=body.collection_name,
            limit=body.limit,
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=body.model,
            max_tokens=settings.anthropic_max_tokens,
            use_web=use_web,
            web_fetch=web_fetch,
            web_fetch_local=web_fetch_local,
        )
        # Defensive: the agent guarantees a title, but never serve a payload
        # that the UI would treat as an empty response.
        if not report or not report.get("title"):
            raise HTTPException(
                status_code=502,
                detail="Model returned an empty report; please retry.",
            )
        return report
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Research report generation failed: {e}",
        )


@router.post("/report/stream")
async def create_research_report_stream(
    body: ReportRequest,
    settings: Settings = Depends(get_settings),
    rag: RAGClient = Depends(get_rag_client),
):
    """Generate a research report, streaming live progress as Server-Sent Events.

    Identical report generation to ``POST /api/research/report``, but the
    response is a ``text/event-stream`` of JSON ``data:`` events so the client
    can show real-time feedback while the agent works:

    - ``{"type": "phase", "message": "...", "tool": "..."}`` — emitted as the
      agent searches the document store, the web, or starts synthesising.
    - ``{"type": "report", "report": {...}}`` — the final structured report.
    - ``{"type": "error", "message": "..."}`` — if generation fails mid-stream.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "ANTHROPIC_API_KEY not configured. "
                "Set it in your .env file to use the research agent."
            ),
        )

    use_web, web_fetch, web_fetch_local = _resolve_web_settings(settings, body)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in stream_report_generation(
                rag_client=rag,
                query=body.query,
                collection_name=body.collection_name,
                limit=body.limit,
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
                model=body.model,
                max_tokens=settings.anthropic_max_tokens,
                use_web=use_web,
                web_fetch=web_fetch,
                web_fetch_local=web_fetch_local,
            ):
                if event["type"] == "report":
                    # Never serve a payload the UI would treat as empty.
                    if not event["report"] or not event["report"].get("title"):
                        yield _sse(
                            {
                                "type": "error",
                                "message": "Model returned an empty report; "
                                "please retry.",
                            }
                        )
                        return
                    yield _sse(event)
                else:
                    yield _sse(event)
        except Exception as e:
            # Keep the stream alive with an error event so the client can
            # surface it inline instead of hanging on a truncated body.
            logger.exception("Research report streaming failed")
            yield _sse(
                {
                    "type": "error",
                    "message": f"Research report generation failed: {e}",
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy/nginx buffering so phases arrive in real time.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ask")
async def ask_question(
    body: AskRequest,
    settings: Settings = Depends(get_settings),
    rag: RAGClient = Depends(get_rag_client),
):
    """Ask a direct question answered from RAG context.

    This is a lighter endpoint than /report — it retrieves relevant
    chunks and answers concisely without a full report structure.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY not configured.",
        )

    # Search RAG
    results = await rag.search(
        query=body.question,
        collection_name=body.collection_name,
        limit=body.limit,
    )

    if not results:
        return {
            "question": body.question,
            "answer": "No relevant documents found to answer this question.",
            "sources": [],
        }

    # Build context
    context_parts = []
    for i, r in enumerate(results, 1):
        source = r.metadata.get("filename", r.parent_doc_id or f"source-{i}")
        context_parts.append(f"[{i}] From {source}:\n{r.content}")
    context = "\n\n".join(context_parts)

    # Use Anthropic directly for a concise answer
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url if settings.anthropic_base_url else None,
    )
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=(
            "You are a helpful research assistant. Answer the user's question "
            "based *only* on the provided document excerpts. If the excerpts "
            "don't contain enough information, say so clearly. Cite sources "
            "using [1], [2] etc."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Context from documents:\n\n{context}\n\n"
                    f"Question: {body.question}"
                ),
            }
        ],
    )

    answer_text = "".join(
        b.text for b in response.content if hasattr(b, "text")
    )

    return {
        "question": body.question,
        "answer": answer_text,
        "sources": [
            {
                "content": r.content[:200],
                "score": r.score,
                "filename": r.metadata.get("filename", r.parent_doc_id),
            }
            for r in results
        ],
    }
