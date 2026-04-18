"""
Configuration management using pydantic-settings.

Loads settings from environment variables and .env file.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Provider Configuration
    llm_provider: Literal["openai", "anthropic", "google"] = "openai"
    llm_model: str = "gpt-4o"

    # API Keys (optional - only the active provider's key is required)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    # Database
    database_path: str = "./data/dev_assistant.db"

    # WhatsApp Session (used by Node bridge)
    whatsapp_session_path: str = "./whatsapp_session"



    # Logging
    log_level: str = "info"

    # Python Bridge Server
    python_bridge_host: str = "127.0.0.1"
    python_bridge_port: int = 8000

    def get_llm_api_key(self) -> str:
        """Get the API key for the configured LLM provider."""
        provider = self.llm_provider.lower()

        if provider == "openai":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            return self.openai_api_key
        elif provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
                )
            return self.anthropic_api_key
        elif provider == "google":
            if not self.google_api_key:
                raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")
            return self.google_api_key
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
