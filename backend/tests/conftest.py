"""Shared test fixtures and helpers.

All external HTTP is mocked with ``httpx.MockTransport`` — no test ever calls
the real FortyGuard API.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from app.core.config import Settings
from app.services.fortyguard_service import FortyGuardService


def make_settings(**overrides: Any) -> Settings:
    """Build a Settings instance with FortyGuard configured for tests."""
    values: dict[str, Any] = {
        "fortyguard_api_key": "test-key-1234",
        "fortyguard_base_url": "https://api.fortyguard.test",
        "fortyguard_temperature_path": "/v1/temperature",
        # Ensure no ambient AI provider leaks into tests.
        "ai_api_key": None,
        "ai_base_url": None,
        "ai_model": None,
    }
    values.update(overrides)
    return Settings(**values)


def transport_json(payload: Any, status_code: int = 200) -> httpx.MockTransport:
    """A MockTransport that always returns ``payload`` as JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


def transport_raising(exc_factory: Callable[[httpx.Request], Exception]) -> httpx.MockTransport:
    """A MockTransport whose handler raises the exception from ``exc_factory``."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_factory(request)

    return httpx.MockTransport(handler)


@pytest.fixture
def configured_settings() -> Settings:
    return make_settings()


def make_service(payload: Any = None, *, status_code: int = 200,
                 transport: httpx.MockTransport | None = None,
                 settings: Settings | None = None) -> FortyGuardService:
    """Construct a FortyGuardService backed by a mock transport."""
    settings = settings or make_settings()
    if transport is None:
        transport = transport_json(payload if payload is not None else {}, status_code)
    return FortyGuardService(settings, transport=transport)
