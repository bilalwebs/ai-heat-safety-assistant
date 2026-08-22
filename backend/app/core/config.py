"""Application configuration.

All settings are loaded from environment variables (or a local ``.env`` file)
via ``pydantic-settings``. Secrets such as API keys are read from the
environment and are never hard-coded.

The FortyGuard section is intentionally "contract-configurable": the exact
endpoint path, authentication header and request style are supplied through
environment variables so the real FortyGuard contract can be plugged in
without code changes. See ``.env.example`` and the README for details.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Application -------------------------------------------------
    app_name: str = "AI Heat Safety Assistant"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # ----- CORS --------------------------------------------------------
    # Comma-separated list of allowed origins. Kept as a string to avoid
    # pydantic-settings attempting to JSON-decode the value from the env.
    cors_allow_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # ----- FortyGuard Temperature API ---------------------------------
    # These values MUST be filled in with the real contract obtained from
    # https://docs-api.fortyguard.com. They are intentionally left unset so
    # the application fails loudly (HTTP 503) rather than calling a guessed
    # endpoint or fabricating data.
    fortyguard_api_key: str | None = None
    fortyguard_base_url: str | None = None
    fortyguard_temperature_path: str | None = None

    # Auth + transport shape (defaults are common conventions; confirm them
    # against the real FortyGuard documentation before relying on them).
    fortyguard_auth_header: str = "Authorization"
    fortyguard_auth_scheme: str = "Bearer"  # set empty for raw-key headers
    fortyguard_http_method: str = "GET"
    fortyguard_request_style: str = "query"  # "query" or "json"
    fortyguard_timeout_seconds: float = 10.0

    # Request parameter names used when building the outgoing call.
    fortyguard_location_param: str = "location"
    fortyguard_lat_param: str = "lat"
    fortyguard_lon_param: str = "lon"

    # ----- AI provider (optional) -------------------------------------
    # If these are unset the AI service falls back to deterministic,
    # data-grounded guidance. If set, an OpenAI-compatible chat endpoint is
    # used. No credentials are ever hard-coded.
    ai_api_key: str | None = None
    ai_base_url: str | None = None  # e.g. https://api.openai.com/v1
    ai_model: str | None = None
    ai_timeout_seconds: float = 30.0

    @property
    def cors_origins_list(self) -> list[str]:
        """Return the configured CORS origins as a clean list."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def fortyguard_configured(self) -> bool:
        """True only when enough is set to attempt a real FortyGuard call."""
        return bool(
            self.fortyguard_api_key
            and self.fortyguard_base_url
            and self.fortyguard_temperature_path
        )

    @property
    def ai_configured(self) -> bool:
        """True when an external AI provider is fully configured."""
        return bool(self.ai_api_key and self.ai_base_url and self.ai_model)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
