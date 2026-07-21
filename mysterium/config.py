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

    # FastAPI server config
    host: str = "0.0.0.0"
    port: int = 8200
    log_level: str = "info"

    # Maximum file upload size via our proxy (bytes)
    max_upload_size: int = 50 * 1024 * 1024  # 50MB


def get_settings() -> Settings:
    """FastAPI dependency that returns application settings."""
    return Settings()
