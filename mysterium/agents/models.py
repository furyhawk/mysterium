"""Structured output models for the research agent.

``ResearchReport`` is the pydantic model the research agent is required to
produce (``output_type=ResearchReport`` in :mod:`mysterium.agents.research`).
The schema is enforced by pydantic-ai — the model must emit a validated report
or nothing at all, so there is no manual JSON wrangling or tool-call fallback
logic downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """A single source used in the report."""

    title: str = Field(description="Title or filename of the source")
    relevance: str = Field(description="Why this source was relevant to the research")
    excerpt: str = Field(description="Key excerpt from the source", max_length=500)


class ReportImage(BaseModel):
    """An image extracted from a source document and cited in the report."""

    image_id: str = Field(description="ID of the image in the RAG document store")
    url: str = Field(
        default="",
        description=(
            "Relative URL path that serves the image, e.g. "
            "/api/v1/images/<image_id>"
        ),
    )
    description: str = Field(
        default="", description="Short caption describing what the image shows"
    )
    page_num: int | None = Field(
        default=None,
        description="Page of the source document the image appears on",
    )
    mime_type: str = Field(default="image/png", description="MIME type of the image")


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
    images: list[ReportImage] = Field(
        default_factory=list,
        description=(
            "Images extracted from source documents that illustrate the report"
        ),
    )
    gaps: list[str] = Field(
        description="Knowledge gaps or areas needing further research"
    )
    generated_at: str = Field(
        default="", description="ISO-8601 timestamp of generation"
    )


__all__ = ["SourceCitation", "ReportImage", "ReportSection", "ResearchReport"]
