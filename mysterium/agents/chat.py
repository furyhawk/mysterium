"""Agentic Q&A chat agent grounded in the RAG document store.

This module provides a conversational, multi-turn Q&A agent backed by the
private verity-rag document store. Unlike the :mod:`mysterium.agents` research
agent — which synthesises a full, structured report — this agent:

- carries a conversation: each turn receives the prior ``ChatMessage`` history
  plus a new user message and answers in context;
- uses RAG as a *tool*: it decides when to call ``rag_search``,
  ``list_collections`` and ``get_report_image`` to ground its answer in the
  user's documents, and can augment with web search / page fetch when enabled;
- streams incremental text tokens and live tool phases, so a chat UI can render
  the answer as it is generated instead of waiting for the whole turn.

The streaming contract mirrors the research agent: a sequence of
``{"type": "phase"|"token"|"message"|"error"}`` events that
:mod:`mysterium.routers.chat` delivers as Server-Sent Events.

The agent is built with a plain pydantic-ai :class:`~pydantic_ai.Agent`
(no deep-agent orchestration) — chat is single-agent tool use, not a
multi-agent research graph.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import WebFetch, WebSearch
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from mysterium.clients.rag_client import RAGClient, RAGImageNotFoundError, SearchResult

logger = logging.getLogger(__name__)


# ── Wire Message Model ─────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in the conversation history (wire format).

    Sent by the client for each turn: ``role`` is ``"user"`` or ``"assistant"``
    and ``content`` is the plain-text message body. The assistant message body
    is the *rendered* text (citations like ``[1]`` are written into it by the
    agent); the structured ``sources`` list is delivered separately in the
    final stream event so the UI can render clickable citations.
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., description="Plain-text message body")


# ── Agent Dependencies ──────────────────────────────────────────────


@dataclass
class ChatDeps:
    """Dependencies for the chat agent.

    ``rag_client`` / ``collection_name`` / ``rag_limit`` back the RAG tools.
    ``sources`` is a per-run collector: the ``rag_search`` tool appends every
    ``SearchResult`` it returns so the final stream event can cite exactly the
    documents the agent actually retrieved.
    """

    rag_client: RAGClient = field(default_factory=RAGClient)
    collection_name: str = "documents"
    rag_limit: int = 5
    sources: list[SearchResult] = field(default_factory=list)


# ── Custom Tools (private RAG) ──────────────────────────────────────


async def rag_search(ctx: RunContext[ChatDeps], query: str, limit: int = 5) -> str:
    """Search the private RAG document store for relevant excerpts.

    Use this to ground your answer in the user's uploaded documents — it is
    the primary source of truth. Each excerpt is labelled
    ``[n] Source: <filename> (score: ...)`` so you can cite it in your answer.

    Args:
        query: The natural-language search query.
        limit: Maximum number of excerpts to return (1-50, default 5).
    """
    limit = max(1, min(int(limit), 50))
    try:
        results = await ctx.deps.rag_client.search(
            query=query,
            collection_name=ctx.deps.collection_name,
            limit=limit,
        )
    except httpx.HTTPError as e:  # Return errors as strings so the agent can recover.
        logger.warning("chat rag_search failed for %r: %s", query, e)
        return f"RAG search failed: {e}"

    if not results:
        return (
            f"No documents in collection {ctx.deps.collection_name!r} matched "
            f"{query!r}. Say so in your answer rather than guessing."
        )

    # Record what was retrieved so the turn can cite the actual sources.
    ctx.deps.sources.extend(results)

    blocks = []
    for i, r in enumerate(results, 1):
        source = r.metadata.get("filename") or r.parent_doc_id or f"result-{i}"
        block = f"[{i}] Source: {source} (score: {r.score:.3f})\n{r.content}"
        if r.images:
            image_lines = []
            for img in r.images:
                caption = f' "{img.description}"' if img.description else ""
                image_lines.append(
                    f"        - image_id={img.image_id} "
                    f"page={img.page_num} mime={img.mime_type}{caption}"
                )
            block += "\n    Images in this result:\n" + "\n".join(image_lines)
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)


async def get_report_image(ctx: RunContext[ChatDeps], image_id: str) -> str:
    """Fetch a document image from the RAG store so it can be shared in chat.

    Use this to validate an image that `rag_search` surfaced (by its
    ``image_id``) before describing it or pointing the user to it. Returns the
    image's size and MIME type as confirmation.

    Args:
        image_id: The image ID shown in a `rag_search` result.
    """
    try:
        data, mime_type = await ctx.deps.rag_client.get_image(image_id)
    except RAGImageNotFoundError:
        return (
            f"Image {image_id!r} was not found on the RAG server — do not "
            "reference it."
        )
    except httpx.HTTPError as e:
        logger.warning("chat get_report_image failed for %r: %s", image_id, e)
        return f"Fetching image {image_id!r} failed: {e}"
    return (
        f"Image {image_id!r} fetched successfully ({mime_type}, "
        f"{len(data)} bytes). You may mention it in your answer and note its "
        "image_id."
    )


async def list_collections(ctx: RunContext[ChatDeps]) -> str:
    """List the names of the available RAG document collections.

    Returns one collection name per line, or a short message when there are
    none.
    """
    try:
        collections = await ctx.deps.rag_client.list_collections()
    except httpx.HTTPError as e:
        logger.warning("chat list_collections failed: %s", e)
        return f"Listing RAG collections failed: {e}"
    if not collections:
        return "No document collections are available."
    return "\n".join(c.name for c in collections)


# ── Agent Factory ───────────────────────────────────────────────────


def _build_system_prompt() -> str:
    """System prompt describing the chat Q&A behaviour."""
    return (
        "You are a helpful, accurate research assistant answering questions "
        "grounded in the user's documents.\n\n"
        "## Workflow\n"
        "1. Use the `rag_search` tool to find relevant excerpts in the private "
        "document store. Start there — the user's documents are the primary "
        "source of truth.\n"
        "2. When the documents are thin, outdated, or the question needs "
        "current public context, use web search and page fetches to fill the "
        "gaps. Prefer authoritative sources.\n"
        "3. Answer the user's question directly and concisely, synthesising "
        "across sources. Cite specific excerpts with the `[n] Source: ...` "
        "labels from `rag_search`, and give URLs for web sources.\n"
        "4. If the documents do not contain the answer, say so explicitly "
        "instead of guessing. Use `list_collections` to discover other "
        "collections when relevant.\n"
        "5. When a document contains relevant images, `rag_search` lists them "
        "(image_id, page, description). Validate one with `get_report_image` "
        "before mentioning it, and note its image_id so the UI can show it.\n\n"
        "## Style\n"
        "- Be conversational but precise; use short paragraphs and bullets.\n"
        "- Always cite sources with [1], [2], ... inline where you use them.\n"
        "- Be honest about uncertainty and contradictions between sources.\n"
        "- Answer follow-up questions in the context of the ongoing "
        "conversation."
    )


def _build_chat_agent(
    *,
    model: str,
    api_key: str,
    base_url: str = "",
    max_tokens: int,
    temperature: float,
    use_web: bool,
    web_fetch: bool,
    web_fetch_local: bool = True,
) -> Agent[ChatDeps, str]:
    """Construct the RAG-grounded chat agent.

    Web search is enabled when ``use_web`` is True (default) so the agent can
    extend the private RAG findings with public information. ``web_fetch``
    toggles page fetching separately, and ``web_fetch_local`` selects HOW it
    runs — mirroring the research agent:

    - ``web_fetch_local=True`` (default): register pydantic-ai's **local**
      fetch tool — ``WebFetch(native=False, local=True)`` — a markdownify-
      based tool that runs in this process. It works with every
      Anthropic-compatible gateway (e.g. DeepSeek), which reject Anthropic's
      server-side ``web_fetch_20250910`` tool with HTTP 400.
    - ``web_fetch_local=False``: use Anthropic's server-side fetch tool.
    """
    provider = AnthropicProvider(api_key=api_key, base_url=base_url or None)
    anthropic_model = AnthropicModel(model_name=model, provider=provider)

    capabilities: list[Any] = []
    if use_web:
        capabilities.append(WebSearch())
    if web_fetch:
        # Local markdownify-based tool works with every Anthropic-compatible
        # gateway; the native tool is the official Anthropic API only.
        capabilities.append(
            WebFetch(native=False, local=True)
            if web_fetch_local
            else WebFetch()
        )

    return Agent(
        model=anthropic_model,
        system_prompt=_build_system_prompt(),
        tools=[rag_search, list_collections, get_report_image],
        deps_type=ChatDeps,
        model_settings={"max_tokens": max_tokens, "temperature": temperature},
        capabilities=capabilities or None,
    )


# ── Message History ────────────────────────────────────────────────


def _to_model_messages(history: list[ChatMessage] | None) -> list[ModelMessage]:
    """Convert wire-format chat history into pydantic-ai ``ModelMessage``s.

    Only user prompts and plain-text assistant turns are reconstructed — tool
    calls from earlier turns are intentionally not replayed; the model receives
    the conversation as plain user/assistant text, which is all it needs for
    follow-up context. pydantic-ai normalises the resulting history, so a
    simple alternating list is safe.
    """
    messages: list[ModelMessage] = []
    for m in history or []:
        if m.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=m.content)]))
    return messages


# ── Streaming Progress ─────────────────────────────────────────────


#: Human-friendly phase labels shown while the agent works, keyed by the tool
#: names pydantic-ai emits in `FunctionToolCallEvent`s as the agent runs.
_TOOL_PHASES: dict[str, str] = {
    "rag_search": "Searching your documents…",
    "list_collections": "Listing document collections…",
    "get_report_image": "Fetching a document image…",
    "web_search": "Searching the web…",
    # The local markdownify tool and Anthropic's server-side web-fetch tool
    # both surface under the same tool name.
    "web_fetch": "Fetching a web page…",
    "web_fetch_20250910": "Fetching a web page…",
}

#: Phase shown once the model starts producing the answer text.
_GENERATING_PHASE = "Generating answer…"


def _progress_phase(message: str, tool: str) -> dict[str, Any]:
    """Build a progress event dict for streaming clients."""
    return {"type": "phase", "message": message, "tool": tool}


def _source_to_dict(result: SearchResult) -> dict[str, Any]:
    """Serialize one RAG source for the final stream event."""
    metadata = result.metadata or {}
    return {
        "filename": metadata.get("filename") or result.parent_doc_id
        or "Unknown source",
        "score": round(result.score, 3),
        "content": (result.content or "")[:400],
        "page": metadata.get("page"),
        "chunk_index": metadata.get("chunk_index"),
    }


def _dedup_sources(sources: list[SearchResult]) -> list[SearchResult]:
    """De-duplicate retrieved sources by chunk id (falling back to content)."""
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for r in sources:
        key = r.chunk_id or (r.content or "")[:200]
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


async def stream_chat_response(
    rag_client: RAGClient,
    message: str,
    *,
    history: list[ChatMessage] | None = None,
    collection_name: str = "documents",
    limit: int = 5,
    api_key: str,
    base_url: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    use_web: bool = True,
    web_fetch: bool = True,
    web_fetch_local: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Run one chat turn, yielding live progress + token events.

    Drives the pydantic-ai agent graph with ``agent.iter()`` and yields:

    - ``{"type": "phase", "message": str, "tool": str}`` — the agent started a
      tool ("Searching your documents…", "Searching the web…", …) or began
      generating the answer.
    - ``{"type": "token", "text": str}`` — an incremental chunk of the answer
      text, so a client can stream it straight into the message bubble.
    - ``{"type": "message", "message": {...}}`` — the final assistant message
      ``{role, content, sources}``. Always the last event.
    - ``{"type": "error", "message": str}`` — raised only as a Python exception
      from this generator; the router converts it to an SSE error event.

    Args:
        rag_client: Connected RAG client.
        message: The user's new message for this turn.
        history: Prior conversation (excluding ``message``).
        collection_name: RAG collection to search.
        limit: Number of RAG results to retrieve per search.
        api_key: Anthropic API key.
        base_url: Optional custom base URL for an Anthropic-compatible gateway.
        model: Claude model name.
        max_tokens: Maximum output tokens.
        temperature: Sampling temperature.
        use_web: Enable web search to augment RAG findings.
        web_fetch: Enable page fetching.
        web_fetch_local: Use a local markdownify-based fetch tool instead of
            Anthropic's server-side web-fetch tool.
    """
    if not api_key:
        raise ValueError("Anthropic API key is required to run the chat agent.")

    agent = _build_chat_agent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
        temperature=temperature,
        use_web=use_web,
        web_fetch=web_fetch,
        web_fetch_local=web_fetch_local,
    )
    deps = ChatDeps(
        rag_client=rag_client,
        collection_name=collection_name,
        rag_limit=limit,
    )
    history_messages = _to_model_messages(history)

    yield _progress_phase("Thinking…", "thinking")

    text_parts: list[str] = []
    generating = False

    # `async with` closes the model's HTTP client after the run so we don't
    # leak connections in the long-running server.
    async with agent:
        async with agent.iter(
            message, deps=deps, message_history=history_messages
        ) as agent_run:
            async for node in agent_run:
                if Agent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            if isinstance(event, PartStartEvent):
                                part = event.part
                                if (
                                    not generating
                                    and getattr(part, "part_kind", None) == "text"
                                ):
                                    generating = True
                                    yield _progress_phase(
                                        _GENERATING_PHASE, "generate"
                                    )
                                # Anthropic delivers the first text chunk inside
                                # the PartStartEvent's TextPart (later chunks
                                # arrive as TextPartDelta events). TestModel
                                # emits an empty part here, so only capture
                                # non-empty content to avoid losing/duplicating
                                # the first token.
                                if isinstance(part, TextPart) and part.content:
                                    text_parts.append(part.content)
                                    yield {
                                        "type": "token",
                                        "text": part.content,
                                    }
                            elif isinstance(event, PartDeltaEvent):
                                delta = event.delta
                                if isinstance(delta, TextPartDelta):
                                    if delta.content_delta:
                                        text_parts.append(delta.content_delta)
                                        yield {
                                            "type": "token",
                                            "text": delta.content_delta,
                                        }
                elif Agent.is_call_tools_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            if isinstance(event, FunctionToolCallEvent):
                                phase = _TOOL_PHASES.get(event.part.tool_name)
                                if phase:
                                    yield _progress_phase(
                                        phase, event.part.tool_name
                                    )

            # Final assistant message with the sources the agent actually used.
            content = "".join(text_parts).strip()
            if not content and agent_run.result is not None:
                # Defensive: if nothing was streamed as text (e.g. a structured
                # edge case), fall back to the run result.
                content = (agent_run.result.output or "").strip()

            sources = [
                _source_to_dict(r)
                for r in sorted(
                    _dedup_sources(deps.sources),
                    key=lambda r: r.score,
                    reverse=True,
                )
            ]
            yield {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "sources": sources,
                    "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            }


async def run_chat_response(
    rag_client: RAGClient,
    message: str,
    *,
    history: list[ChatMessage] | None = None,
    collection_name: str = "documents",
    limit: int = 5,
    api_key: str,
    base_url: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    use_web: bool = True,
    web_fetch: bool = True,
    web_fetch_local: bool = True,
) -> dict[str, Any]:
    """Run one chat turn and return the final assistant message (no streaming).

    Convenience wrapper around :func:`stream_chat_response` that discards the
    intermediate phase/token events and returns only the final message dict
    (``role``, ``content``, ``sources``).

    Args:
        Same as :func:`stream_chat_response`.

    Returns:
        The assistant message as a dict.
    """
    final: dict[str, Any] | None = None
    async for event in stream_chat_response(
        rag_client=rag_client,
        message=message,
        history=history,
        collection_name=collection_name,
        limit=limit,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        use_web=use_web,
        web_fetch=web_fetch,
        web_fetch_local=web_fetch_local,
    ):
        if event["type"] == "message":
            final = event["message"]

    if final is None:
        raise RuntimeError("Chat agent finished without producing a message.")
    return final
