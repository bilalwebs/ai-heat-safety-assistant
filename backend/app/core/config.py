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
    # Contract verified against the official client
    # (github.com/FortyGuard-Tech/temperature-api-quickstart):
    #   * host https://api.fortyguard.com
    #   * auth header  `api-key: <key>`  (NOT `Authorization: Bearer`)
    #   * async: submit POST /v1/heatmap -> poll GET /v1/status/{activity_id}
    # The key and base URL come from the environment; nothing is hard-coded.
    fortyguard_api_key: str | None = None
    fortyguard_base_url: str | None = None

    # Legacy single-shot temperature endpoint path. NOT used by the async
    # heatmap integration; the /temperature endpoint stays 503 until it is set
    # (the real API has no such point-lookup — see README "Known gaps").
    fortyguard_temperature_path: str | None = None

    # Auth + transport shape. Defaults match the verified FortyGuard contract:
    # a raw `api-key` header with no scheme prefix.
    fortyguard_auth_header: str = "api-key"
    fortyguard_auth_scheme: str = ""  # empty -> raw key, no "Bearer " prefix
    fortyguard_http_method: str = "GET"
    fortyguard_request_style: str = "query"  # "query" or "json"
    fortyguard_timeout_seconds: float = 10.0

    # Async heatmap workflow (submit -> poll). The request-scoped wait is
    # bounded so an HTTP request never hangs for the full upstream budget.
    fortyguard_poll_interval_seconds: float = 3.0
    fortyguard_max_wait_seconds: float = 25.0

    # Request parameter names used by the legacy temperature call.
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
    def fortyguard_ready(self) -> bool:
        """True when the async FortyGuard API (heatmap) can be called.

        Only an API key and base URL are required: the async endpoints
        (/v1/heatmap, /v1/status/{id}) are fixed and need no path config.
        """
        return bool(self.fortyguard_api_key and self.fortyguard_base_url)

    @property
    def ai_configured(self) -> bool:
        """True when an external AI provider is fully configured."""
        return bool(self.ai_api_key and self.ai_base_url and self.ai_model)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
