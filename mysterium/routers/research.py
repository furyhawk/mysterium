"""Research and report generation router.

Uses pydantic-deep agents to synthesise structured research reports
from RAG-retrieved documents and LLM analysis.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mysterium.agents import generate_research_report
from mysterium.clients.rag_client import RAGClient
from mysterium.config import Settings, get_settings

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


class AskRequest(BaseModel):
    """Parameters for quick Q&A."""

    question: str = Field(..., min_length=1)
    collection_name: str = "documents"
    limit: int = Field(default=5, ge=1, le=50)


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

    try:
        report = await generate_research_report(
            rag_client=rag,
            query=body.query,
            collection_name=body.collection_name,
            limit=body.limit,
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=body.model,
        )
        return report
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Research report generation failed: {e}",
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
