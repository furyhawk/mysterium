"""Agentic Q&A chat router.

Exposes the RAG-grounded chat agent over HTTP for a conversational UI:

- ``POST /api/chat``          — blocking single-turn Q&A, returns the assistant
  message (content + cited sources) when done.
- ``POST /api/chat/stream``   — the same turn as Server-Sent Events, with live
  tool phases and incremental text tokens before the final ``message`` event.

The client owns the conversation: it sends the full prior ``messages`` history
plus the new ``message`` each turn, so the server stays stateless. The
streaming event contract is:

- ``{"type": "phase", "message": str, "tool": str}`` — the agent started a
  tool ("Searching your documents…", "Searching the web…") or the answer.
- ``{"type": "token", "text": str}`` — an incremental chunk of answer text.
- ``{"type": "message", "message": {role, content, sources}}`` — final message.
- ``{"type": "error", "message": str}`` — if the turn fails mid-stream.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from mysterium.agents.chat import ChatMessage, run_chat_response, stream_chat_response
from mysterium.clients.rag_client import RAGClient
from mysterium.config import Settings, get_settings
from mysterium.history import HistoryStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def get_rag_client(settings: Settings = Depends(get_settings)) -> RAGClient:
    """Dependency providing a connected RAG client."""
    return RAGClient(base_url=settings.rag_server_url)


class ChatRequest(BaseModel):
    """One chat turn request."""

    message: str = Field(..., min_length=1, description="The user's new message")
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description=(
            "Prior conversation history (excluding `message`). The client "
            "owns the conversation; the server is stateless."
        ),
    )
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Stable id for this conversation, used to persist the transcript "
            "server-side. Omit to start a new conversation — the server "
            "assigns an id and returns it in the response so later turns can "
            "continue the same transcript."
        ),
    )
    collection_name: str = "documents"
    limit: int = Field(default=5, ge=1, le=50)
    model: str = "claude-sonnet-4-20250514"
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    use_web: bool | None = Field(
        default=None,
        description=(
            "Augment RAG findings with web search. "
            "Defaults to the server CHAT_USE_WEB setting."
        ),
    )
    use_web_fetch: bool | None = Field(
        default=None,
        description=(
            "Fetch full web pages to augment RAG findings. "
            "Defaults to the server CHAT_WEB_FETCH setting."
        ),
    )
    use_web_fetch_local: bool | None = Field(
        default=None,
        description=(
            "Fetch pages with a local markdownify-based tool instead of "
            "Anthropic's server-side web-fetch tool. Works with every "
            "Anthropic-compatible gateway. Defaults to the server "
            "CHAT_WEB_FETCH_LOCAL setting."
        ),
    )


def _resolve_web_settings(
    settings: Settings, body: ChatRequest
) -> tuple[bool, bool, bool]:
    """Resolve web search/fetch toggles from request > env settings.

    Returns ``(use_web, web_fetch, web_fetch_local)`` — the effective values
    shared by the blocking and the streaming chat endpoints. Mirrors the
    research router's resolution logic.
    """
    use_web = settings.chat_use_web if body.use_web is None else body.use_web

    # web_fetch_local: request > CHAT_WEB_FETCH_LOCAL setting > True.
    if body.use_web_fetch_local is not None:
        web_fetch_local = body.use_web_fetch_local
    else:
        web_fetch_local = settings.chat_web_fetch_local

    # The server-side web-fetch tool is rejected by most Anthropic-compatible
    # gateways. Explicitly configured CHAT_WEB_FETCH wins; otherwise auto:
    # fetch stays on for the official Anthropic API (no custom base URL), AND
    # for custom gateways whenever the local fetch tool is in use — the local
    # markdownify tool works with every gateway. Fetch is only auto-disabled
    # for gateways when falling back to the server-side tool.
    if body.use_web_fetch is not None:
        web_fetch = body.use_web_fetch
    elif settings.chat_web_fetch is not None:
        web_fetch = settings.chat_web_fetch
    else:
        web_fetch = web_fetch_local or not bool(settings.anthropic_base_url)

    return use_web, web_fetch, web_fetch_local


def _sse(event: dict) -> str:
    """Encode a single JSON object as a Server-Sent Event."""
    return f"data: {json.dumps(event)}\n\n"


def _require_api_key(settings: Settings) -> None:
    """Raise a 400 when no Anthropic API key is configured."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "ANTHROPIC_API_KEY not configured. "
                "Set it in your .env file to use the chat agent."
            ),
        )


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    settings: Settings = Depends(get_settings),
    rag: RAGClient = Depends(get_rag_client),
):
    """Answer a question, streaming live tokens and phases as Server-Sent Events.

    The agent searches the RAG document store (and optionally the web) to
    ground its answer, then streams the answer text as ``token`` events. The
    stream always ends with a ``message`` event carrying the full assistant
    message and the cited sources, or an ``error`` event if it fails.
    """
    _require_api_key(settings)
    use_web, web_fetch, web_fetch_local = _resolve_web_settings(settings, body)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in stream_chat_response(
                rag_client=rag,
                message=body.message,
                history=body.messages,
                collection_name=body.collection_name,
                limit=body.limit,
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
                model=body.model,
                max_tokens=settings.anthropic_max_tokens,
                temperature=body.temperature,
                use_web=use_web,
                web_fetch=web_fetch,
                web_fetch_local=web_fetch_local,
            ):
                # Never serve an empty assistant message the UI can't render.
                if (
                    event["type"] == "message"
                    and not event["message"].get("content")
                ):
                    yield _sse(
                        {
                            "type": "error",
                            "message": "Model returned an empty answer; "
                            "please retry.",
                        }
                    )
                    return
                # Persist the turn (non-fatal) and surface the conversation id
                # so the client can continue the same transcript later.
                if event["type"] == "message":
                    message = event["message"]
                    conversation_id = body.conversation_id or uuid.uuid4().hex
                    HistoryStore(
                        root=settings.data_dir,
                        enabled=settings.history_enabled,
                    ).append_chat(
                        conversation_id,
                        user_message=body.message,
                        assistant_message=message,
                        collection_name=body.collection_name,
                    )
                    event = {
                        **event,
                        "message": {
                            **message,
                            "conversation_id": conversation_id,
                        },
                    }
                yield _sse(event)
        except Exception as e:
            # Keep the stream alive with an error event so the client can
            # surface it inline instead of hanging on a truncated body.
            logger.exception("Chat streaming failed")
            yield _sse(
                {
                    "type": "error",
                    "message": f"Chat failed: {e}",
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy/nginx buffering so tokens arrive in real time.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("")
async def chat(
    body: ChatRequest,
    settings: Settings = Depends(get_settings),
    rag: RAGClient = Depends(get_rag_client),
):
    """Answer a question and return the assistant message when done.

    Blocking counterpart of ``POST /api/chat/stream`` — same agent, same
    sources, but no live tokens. Useful for simple clients or quick tests.
    """
    _require_api_key(settings)
    use_web, web_fetch, web_fetch_local = _resolve_web_settings(settings, body)
    try:
        result = await run_chat_response(
            rag_client=rag,
            message=body.message,
            history=body.messages,
            collection_name=body.collection_name,
            limit=body.limit,
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=body.model,
            max_tokens=settings.anthropic_max_tokens,
            temperature=body.temperature,
            use_web=use_web,
            web_fetch=web_fetch,
            web_fetch_local=web_fetch_local,
        )
        if not result.get("content"):
            raise HTTPException(
                status_code=502,
                detail="Model returned an empty answer; please retry.",
            )
        # Persist the turn (non-fatal) and surface the conversation id so the
        # client can continue the same transcript on later turns.
        conversation_id = body.conversation_id or uuid.uuid4().hex
        HistoryStore(
            root=settings.data_dir, enabled=settings.history_enabled
        ).append_chat(
            conversation_id,
            user_message=body.message,
            assistant_message=result,
            collection_name=body.collection_name,
        )
        return {**result, "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {e}",
        )
