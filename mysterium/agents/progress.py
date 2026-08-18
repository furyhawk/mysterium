"""Human-friendly progress phases emitted while an agent runs.

Both the research and chat agents stream ``{"type": "phase", ...}`` events so
clients can show live feedback ("Searching your documents…", "Searching the
web…", …). This module centralises the phase labels and the event builder,
shared by :mod:`mysterium.agents.research` and :mod:`mysterium.agents.chat`.
"""

from __future__ import annotations

from typing import Any

#: Human-friendly phase labels shown while the agent works, keyed by the tool
#: names pydantic-ai emits in `FunctionToolCallEvent`s as the agent runs.
TOOL_PHASES: dict[str, str] = {
    "rag_search": "Searching your documents…",
    "list_collections": "Listing document collections…",
    "get_report_image": "Fetching a document image…",
    "web_search": "Searching the web…",
    # The local markdownify tool and Anthropic's server-side web-fetch tool
    # both surface under the same tool name.
    "web_fetch": "Fetching a web page…",
    "web_fetch_20250910": "Fetching a web page…",
}

#: Phase shown once the model starts emitting the structured report.
SYNTHESIS_PHASE = "Synthesizing the final report…"

#: Phase shown once the chat model starts producing the answer text.
GENERATING_PHASE = "Generating answer…"


def progress_phase(message: str, tool: str) -> dict[str, Any]:
    """Build a progress event dict for streaming clients."""
    return {"type": "phase", "message": message, "tool": tool}


__all__ = ["TOOL_PHASES", "SYNTHESIS_PHASE", "GENERATING_PHASE", "progress_phase"]
