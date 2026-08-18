"""Research agent construction and report generation.

This module builds the headless pydantic-deep agent (``_build_research_agent``)
and drives it to produce a structured :class:`~mysterium.agents.models.ResearchReport`:

- :func:`stream_research_report` runs the agent and yields live progress
  events (tool phases) followed by the final report event.
- :func:`generate_research_report` is a convenience wrapper that discards the
  progress events and returns only the final report dict.

Web search is enabled by default so the agent can extend the private RAG
findings with public information. Page fetching is controlled separately and
defaults to a **local** markdownify-based tool (see ``web_fetch_local``),
which works with every Anthropic-compatible gateway.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.agent import Agent
from pydantic_ai.capabilities import WebFetch
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    OutputToolCallEvent,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_deep import DeepAgentDeps, StateBackend, create_deep_agent

from mysterium.agents.deps import ResearchDeps
from mysterium.agents.models import ResearchReport
from mysterium.agents.progress import SYNTHESIS_PHASE, TOOL_PHASES, progress_phase
from mysterium.agents.prompt import build_system_prompt
from mysterium.agents.tools import get_report_image, list_collections, rag_search
from mysterium.clients.rag_client import RAGClient

logger = logging.getLogger(__name__)


# ── Agent Factory ───────────────────────────────────────────────────


def _build_research_agent(
    *,
    model: str,
    api_key: str,
    base_url: str = "",
    max_tokens: int,
    use_web: bool,
    web_fetch: bool,
    web_fetch_local: bool = True,
) -> Agent[DeepAgentDeps, ResearchReport]:
    """Construct a headless deep agent that researches and returns a report.

    Web search is enabled when ``use_web`` is True (the default) so the agent
    can extend the private RAG findings with public information. ``web_fetch``
    toggles page fetching separately, and ``web_fetch_local`` selects HOW it
    runs:

    - ``web_fetch_local=True`` (default): register pydantic-ai's **local**
      fetch tool — ``WebFetch(native=False, local=True)`` — a markdownify-
      based tool that runs in this process. It works with every
      Anthropic-compatible gateway (e.g. DeepSeek), which reject Anthropic's
      server-side ``web_fetch_20250910`` tool with HTTP 400.
    - ``web_fetch_local=False``: use Anthropic's server-side fetch tool via
      ``create_deep_agent(web_fetch=True)`` (official Anthropic API only).

    Interactive capabilities (filesystem, shell, subagents, planning,
    persistent memory) are disabled — this is a single-shot API task.
    """
    provider = AnthropicProvider(api_key=api_key, base_url=base_url or None)
    anthropic_model = AnthropicModel(model_name=model, provider=provider)

    # Web fetch strategy. pydantic-deep's `web_fetch=True` registers the
    # native Anthropic server-side tool, which most Anthropic-compatible
    # gateways reject. In local mode we disable that capability and instead
    # register pydantic-ai's markdownify-based local fetch tool through the
    # generic `capabilities` hook.
    capabilities: list[Any] | None = None
    server_web_fetch = web_fetch
    if web_fetch and web_fetch_local:
        capabilities = [WebFetch(native=False, local=True)]
        server_web_fetch = False

    return create_deep_agent(
        model=anthropic_model,
        instructions=build_system_prompt(),
        tools=[rag_search, list_collections, get_report_image],
        output_type=ResearchReport,
        # Web tools: search + fetch are independently toggleable. In local
        # fetch mode `web_fetch=False` here because the local capability is
        # passed via `capabilities` — the server-side tool stays off entirely.
        web_search=use_web,
        web_fetch=server_web_fetch,
        capabilities=capabilities,
        # Structured synthesis budget.
        model_settings={"max_tokens": max_tokens, "temperature": 0.3},
        # In-memory backend — nothing is written to disk for a single run.
        backend=StateBackend(),
        # Headless API mode: disable interactive capabilities we don't need.
        include_filesystem=False,
        include_subagents=False,
        include_plan=False,
        include_builtin_subagents=False,
        include_skills=False,
        include_memory=False,
        context_manager=True,
        include_history_archive=False,
        cost_tracking=False,
        thinking=False,
    )


# ── Report Generation ──────────────────────────────────────────────


async def stream_research_report(
    rag_client: RAGClient,
    query: str,
    *,
    collection_name: str = "documents",
    limit: int = 10,
    api_key: str,
    base_url: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 32768,
    use_web: bool = True,
    web_fetch: bool = True,
    web_fetch_local: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Run the research agent, yielding live progress events.

    This is the streaming counterpart of :func:`generate_research_report`.
    Instead of blocking until the whole report is ready, it drives the
    pydantic-ai agent graph with ``agent.iter()`` and yields a progress event
    the moment the agent starts a tool, so a client can show live feedback
    ("Searching your documents…", "Searching the web…", …).

    Each yielded item is one of:

    - ``{"type": "phase", "message": str, "tool": str}`` — a phase change
      (the agent started a tool or the final report output).
    - ``{"type": "report", "report": dict}`` — the final structured report.
      This is always the last event.

    Args:
        Same as :func:`generate_research_report`.
    """
    if not api_key:
        raise ValueError("Anthropic API key is required to run the research agent.")

    agent = _build_research_agent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
        use_web=use_web,
        web_fetch=web_fetch,
        web_fetch_local=web_fetch_local,
    )
    deps = ResearchDeps(
        backend=StateBackend(),
        rag_client=rag_client,
        collection_name=collection_name,
        rag_limit=limit,
    )

    user_prompt = (
        f"Research the following topic thoroughly:\n\n{query}\n\n"
        "Search the private document store first, then use web sources to fill "
        "gaps where needed. Produce the final structured report."
    )

    yield progress_phase("Preparing the research agent…", "init")

    # `async with` closes the model's HTTP client after the run so we don't
    # leak connections in the long-running server.
    async with agent:
        # `agent.iter()` streams the agent graph node-by-node. ModelRequestNode
        # yields the model's response events (including FinalResultEvent once
        # the structured output matches the schema); CallToolsNode yields
        # FunctionToolCallEvent/FunctionToolResultEvent as tools execute.
        async with agent.iter(user_prompt, deps=deps) as agent_run:
            async for node in agent_run:
                if Agent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for _event in stream:
                            if isinstance(_event, FinalResultEvent):
                                yield progress_phase(SYNTHESIS_PHASE, "final_result")
                elif Agent.is_call_tools_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:
                            if isinstance(event, FunctionToolCallEvent):
                                phase = TOOL_PHASES.get(event.part.tool_name)
                                if phase:
                                    yield progress_phase(phase, event.part.tool_name)
                            elif isinstance(event, OutputToolCallEvent):
                                yield progress_phase(SYNTHESIS_PHASE, "final_result")

            if agent_run.result is not None:
                report = agent_run.result.output
                report.generated_at = datetime.datetime.now(datetime.UTC).isoformat()
                yield {"type": "report", "report": report.model_dump()}


async def generate_research_report(
    rag_client: RAGClient,
    query: str,
    *,
    collection_name: str = "documents",
    limit: int = 10,
    api_key: str,
    base_url: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 32768,
    use_web: bool = True,
    web_fetch: bool = True,
    web_fetch_local: bool = True,
) -> dict[str, Any]:
    """Generate a structured research report using a pydantic-deep agent.

    The agent is given RAG search tools (backed by ``rag_client``) and, when
    ``use_web`` is True, web search capabilities. ``web_fetch`` independently
    controls page fetching, and ``web_fetch_local`` selects a local
    markdownify-based fetch tool (default) instead of Anthropic's server-side
    one. Structured output is enforced via ``output_type=ResearchReport``.

    This is a convenience wrapper around :func:`stream_research_report` that
    discards the intermediate progress events and returns only the final
    report.

    Args:
        rag_client: Connected RAG client.
        query: Research question or topic.
        collection_name: RAG collection to search.
        limit: Number of RAG results to retrieve.
        api_key: Anthropic API key.
        base_url: Optional custom base URL for an Anthropic-compatible gateway.
        model: Claude model name.
        max_tokens: Maximum output tokens.
        use_web: Enable web search to augment RAG findings.
        web_fetch: Enable page fetching.
        web_fetch_local: Use a local markdownify-based fetch tool instead of
            Anthropic's server-side web-fetch tool. Local fetching works with
            every Anthropic-compatible gateway (which typically reject the
            server-side ``web_fetch_20250910`` tool), so it defaults to True.

    Returns:
        Structured ResearchReport as a dict.
    """
    report: dict[str, Any] | None = None
    async for event in stream_research_report(
        rag_client=rag_client,
        query=query,
        collection_name=collection_name,
        limit=limit,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        use_web=use_web,
        web_fetch=web_fetch,
        web_fetch_local=web_fetch_local,
    ):
        if event["type"] == "report":
            report = event["report"]

    if report is None:
        raise RuntimeError("Research agent finished without producing a report.")
    return report


__all__ = ["stream_research_report", "generate_research_report"]
