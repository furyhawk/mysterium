"""Application configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Mysterium application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # verity-rag server URL
    rag_server_url: str = "http://localhost:8100"

    # Anthropic API key for research agent
    anthropic_api_key: str = ""
    # Optional: custom base URL for Anthropic-compatible gateway
    anthropic_base_url: str = ""
    # Maximum output tokens for research report generation
    anthropic_max_tokens: int = 32768

    # Augment RAG research with web search (default: on)
    research_use_web: bool = True

    # Enable web page fetch. None (default) = auto: enabled with the official
    # Anthropic API, but disabled when a custom ANTHROPIC_BASE_URL gateway is
    # used AND the local fetch tool is off — most Anthropic-compatible
    # gateways (e.g. DeepSeek) reject the server-side `web_fetch_20250910`
    # tool with HTTP 400.
    research_web_fetch: bool | None = None

    # Fetch web pages with a LOCAL markdownify-based tool (pydantic-ai's
    # `WebFetch(native=False, local=True)`) instead of Anthropic's server-side
    # `web_fetch` tool. Local fetching runs in this process and works with
    # every Anthropic-compatible gateway, so it defaults to True.
    research_web_fetch_local: bool = True

    # Agentic Q&A chat agent — augment RAG answers with web search
    chat_use_web: bool = True

    # Enable web page fetch for the chat agent. None (default) = auto: enabled
    # with the official Anthropic API, disabled when a custom ANTHROPIC_BASE_URL
    # gateway is used AND the local fetch tool is off (gateways reject the
    # server-side `web_fetch_20250910` tool).
    chat_web_fetch: bool | None = None

    # Fetch web pages with a LOCAL markdownify-based tool for the chat agent.
    # Works with every Anthropic-compatible gateway, so it defaults to True.
    chat_web_fetch_local: bool = True

    # FastAPI server config
    host: str = "0.0.0.0"
    port: int = 8200
    log_level: str = "info"

    # Maximum file upload size via our proxy (bytes)
    max_upload_size: int = 50 * 1024 * 1024  # 50MB


def get_settings() -> Settings:
    """FastAPI dependency that returns application settings."""
    return Settings()
