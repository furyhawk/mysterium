"""Dependencies for the research agent.

``ResearchDeps`` extends pydantic-deep's ``DeepAgentDeps`` with RAG access.
It is injected by pydantic-ai into every tool call via ``ctx.deps``, so the
RAG tools in :mod:`mysterium.agents.tools` can reach the verity-rag client and
the current query settings without global state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_deep import DeepAgentDeps

from mysterium.clients.rag_client import RAGClient


@dataclass
class ResearchDeps(DeepAgentDeps):
    """Deep-agent dependencies extended with RAG access.

    The custom tools read the verity-rag client and query settings from
    ``ctx.deps``, which pydantic-ai injects at call time.

    ``rag_client`` has a default factory only so the dataclass ordering rules
    allow the extra fields after ``DeepAgentDeps``' defaulted ones — every run
    passes a real client built from the request settings.
    """

    rag_client: RAGClient = field(default_factory=RAGClient)
    collection_name: str = "documents"
    rag_limit: int = 10


__all__ = ["ResearchDeps"]
