"""Research agent powered by pydantic-deep.

Synthesizes research reports by searching the RAG document store and
optionally augmenting with web search results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from mysterium.clients.rag_client import RAGClient


# ── Structured Output Models ────────────────────────────────────────


class SourceCitation(BaseModel):
    """A single source used in the report."""

    title: str = Field(description="Title or filename of the source")
    relevance: str = Field(description="Why this source was relevant to the research")
    excerpt: str = Field(description="Key excerpt from the source", max_length=500)


class ReportSection(BaseModel):
    """A section of the research report."""

    heading: str = Field(description="Section heading")
    content: str = Field(description="Section body text")
    sources: list[str] = Field(
        description="Source identifiers referenced in this section"
    )


class ResearchReport(BaseModel):
    """A structured research report synthesised from RAG and web sources."""

    title: str = Field(description="Report title")
    summary: str = Field(description="Executive summary (2-3 paragraphs)")
    key_findings: list[str] = Field(description="Key findings extracted from the research")
    sections: list[ReportSection] = Field(description="Detailed report sections")
    sources: list[SourceCitation] = Field(description="All sources cited in the report")
    gaps: list[str] = Field(
        description="Knowledge gaps or areas needing further research"
    )
    generated_at: str = Field(description="ISO-8601 timestamp of generation")


# ── Agent Implementation ────────────────────────────────────────────


class RAGResearchTool:
    """A tool that wraps RAG search for use by the LLM."""

    def __init__(self, rag_client: RAGClient) -> None:
        self._rag = rag_client

    def search_documents(
        self,
        query: str,
        collection_name: str = "documents",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the RAG document store for relevant content.

        Args:
            query: The search query.
            collection_name: Collection to search (default: "documents").
            limit: Maximum results to return (default: 10, max: 50).

        Returns:
            List of search results with content, score, and metadata.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            coro = self._rag.search(
                query=query,
                collection_name=collection_name,
                limit=min(limit, 50),
            )
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            results = fut.result(timeout=60)
        else:
            results = asyncio.run(
                self._rag.search(
                    query=query,
                    collection_name=collection_name,
                    limit=min(limit, 50),
                )
            )

        return [
            {
                "content": r.content,
                "score": r.score,
                "source_doc": r.parent_doc_id,
                "metadata": r.metadata,
            }
            for r in results
        ]

    def list_collections(self) -> list[str]:
        """List all available document collections."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            coro = self._rag.list_collections()
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            collections = fut.result(timeout=30)
        else:
            collections = asyncio.run(self._rag.list_collections())

        return [c.name for c in collections]


def _build_system_prompt(rag_context: str) -> str:
    """Build the system prompt for the research agent."""
    return f"""You are a research synthesis agent. Your job is to produce a thorough,
well-structured research report based on the retrieved document content and,
when relevant, your own knowledge.

## Available context from the RAG system
The following content was retrieved from the document store. Use it as your
primary source material:

{rag_context}

## Guidelines
1. Synthesise across sources — don't just summarise each document in turn.
2. Cite specific excerpts to support claims.
3. Identify contradictions or disagreements between sources.
4. Note knowledge gaps — what's missing or uncertain.
5. Structure the report logically with clear sections.
6. Write in a neutral, academic tone.
7. If the RAG results are empty or insufficient, say so clearly and
   produce a preliminary report based on general knowledge, noting the
   lack of specific document sources."""


async def generate_research_report(
    rag_client: RAGClient,
    query: str,
    *,
    collection_name: str = "documents",
    limit: int = 10,
    api_key: str,
    base_url: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Generate a structured research report using Anthropic directly.

    This approach uses the Anthropic API directly rather than going through
    pydantic-deep's full agent harness, because the agent harness requires
    interactive capabilities (filesystem, shell, etc.) that aren't needed
    for a headless synthesis task. The structured output is enforced via
    tool use.

    Args:
        rag_client: Connected RAG client.
        query: Research question or topic.
        collection_name: RAG collection to search.
        limit: Number of RAG results to retrieve.
        api_key: Anthropic API key.
        base_url: Optional custom base URL for an Anthropic-compatible gateway.
        model: Claude model name.
        max_tokens: Maximum output tokens.
        max_tokens: Maximum output tokens.

    Returns:
        Structured ResearchReport as a dict.
    """
    # 1. Search RAG
    rag_results = await rag_client.search(
        query=query,
        collection_name=collection_name,
        limit=limit,
    )

    # Format RAG context for the prompt
    if rag_results:
        rag_sections = []
        for i, r in enumerate(rag_results, 1):
            source_label = r.parent_doc_id or f"result-{i}"
            meta_str = (
                f"Source: {r.metadata.get('filename', source_label)} "
                f"(score: {r.score:.3f})"
            )
            rag_sections.append(f"[{i}] {meta_str}\n{r.content}\n")
        rag_context = "\n---\n".join(rag_sections)
    else:
        rag_context = (
            "No relevant documents found in the RAG store. "
            "Note this in your report."
        )

    # 2. Build the structured output schema for tool use
    system_prompt = _build_system_prompt(rag_context)

    client = AsyncAnthropic(
        api_key=api_key,
        base_url=base_url if base_url else None,
    )

    response = await client.beta.messages.with_raw_types.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt}],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Research the following topic thoroughly:\n\n{query}\n\n"
                    f"Produce a structured report using the available tools."
                ),
            }
        ],
        tools=[
            {
                "name": "submit_report",
                "description": "Submit the final structured research report",
                "input_schema": ResearchReport.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "submit_report"},
    )

    # 3. Parse the tool call output
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_report":
            report = block.input
            report["generated_at"] = datetime.now().isoformat()
            return report

    # Fallback: return raw text wrapped in structure
    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
    raw = "\n".join(text_blocks) if text_blocks else str(response.content)

    return ResearchReport(
        title=f"Research: {query}",
        summary=raw[:1000],
        key_findings=[],
        sections=[
            ReportSection(
                heading="Raw Response",
                content=raw,
                sources=[],
            )
        ],
        sources=[
            SourceCitation(
                title=r.metadata.get("filename", f"result-{i}"),
                relevance="Retrieved from RAG search",
                excerpt=r.content[:300],
            )
            for i, r in enumerate(rag_results[:5])
        ],
        gaps=[],
        generated_at=datetime.now().isoformat(),
    ).model_dump()
