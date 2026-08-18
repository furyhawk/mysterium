"""Shared RAG tools used by the research and chat agents.

These tools query the private verity-rag document store through ``ctx.deps``
and return their findings as plain strings so the model can read and cite
them. They work with any deps exposing ``rag_client`` and ``collection_name``
(see :class:`RagToolsDeps`); when the deps also carries the optional
``sources`` / ``images`` / ``validated_image_ids`` collectors (as
:class:`~mysterium.agents.chat.ChatDeps` does), the tools record what they
retrieved/validated so the caller can render citations and images.

Errors are returned as message strings rather than raised — the agent can
recover and note the problem in its output.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from pydantic_ai import RunContext

from mysterium.clients.rag_client import (
    RAGClient,
    RAGImageNotFoundError,
    SearchResult,
    SearchResultImage,
)

logger = logging.getLogger(__name__)


class RagToolsDeps(Protocol):
    """Minimal deps contract for the shared RAG tools.

    Agent deps must expose ``rag_client`` and ``collection_name``. Deps may
    additionally carry ``sources`` / ``images`` / ``validated_image_ids``
    collector attributes (see :class:`~mysterium.agents.chat.ChatDeps`); when
    present, the tools record what they retrieved/validated so the caller can
    render citations and images. Deps without them are left untouched.
    """

    rag_client: RAGClient
    collection_name: str


def _record_sources(deps: RagToolsDeps, results: list[SearchResult]) -> None:
    """Record retrieved results (and the images they surface) on chat-like deps."""
    sources = getattr(deps, "sources", None)
    if sources is not None:
        sources.extend(results)
    images = getattr(deps, "images", None)
    if images is not None:
        for r in results:
            if r.images:
                images.extend(r.images)


def _record_validated_image(
    deps: RagToolsDeps, image_id: str, mime_type: str
) -> None:
    """Mark an image as validated on chat-like deps so the UI can render it."""
    validated = getattr(deps, "validated_image_ids", None)
    if validated is None:
        return
    validated.add(image_id)
    images = getattr(deps, "images", None)
    if images is not None and not any(img.image_id == image_id for img in images):
        images.append(SearchResultImage(image_id=image_id, mime_type=mime_type))


def format_search_results(results: list[SearchResult]) -> str:
    """Render RAG results as labelled, cite-able blocks for the model."""
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


async def rag_search(ctx: RunContext[RagToolsDeps], query: str, limit: int = 5) -> str:
    """Search the private RAG document store for relevant excerpts.

    Use this to find information in the user's uploaded documents — it is the
    primary source material. Each excerpt is labelled
    ``[n] Source: <filename> (score: ...)`` so you can cite it.

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
        logger.warning("rag_search failed for %r: %s", query, e)
        return f"RAG search failed: {e}"

    if not results:
        return (
            f"No documents in collection {ctx.deps.collection_name!r} matched "
            f"{query!r}. Be explicit about this gap — do not fabricate content."
        )

    _record_sources(ctx.deps, results)
    return format_search_results(results)


async def get_report_image(ctx: RunContext[RagToolsDeps], image_id: str) -> str:
    """Fetch a document image from the RAG store so it can be cited in a response.

    Use this to validate an image that `rag_search` surfaced (by its
    ``image_id``) before including it in your output. Returns the image's size
    and MIME type as confirmation.

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
        logger.warning("get_report_image failed for %r: %s", image_id, e)
        return f"Fetching image {image_id!r} failed: {e}"
    _record_validated_image(ctx.deps, image_id, mime_type)
    return (
        f"Image {image_id!r} fetched successfully ({mime_type}, "
        f"{len(data)} bytes). You may cite it in your response using its "
        "image_id."
    )


async def list_collections(ctx: RunContext[RagToolsDeps]) -> str:
    """List the names of the available RAG document collections.

    Returns one collection name per line, or a short message when there are
    none.
    """
    try:
        collections = await ctx.deps.rag_client.list_collections()
    except httpx.HTTPError as e:
        logger.warning("list_collections failed: %s", e)
        return f"Listing RAG collections failed: {e}"
    if not collections:
        return "No document collections are available."
    return "\n".join(c.name for c in collections)


__all__ = [
    "RagToolsDeps",
    "format_search_results",
    "rag_search",
    "get_report_image",
    "list_collections",
]
