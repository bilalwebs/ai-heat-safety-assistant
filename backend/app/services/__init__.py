"""Service layer: business logic and external API communication.

Exposes cached service singletons and small orchestration helpers used by the
routers. Keeping construction here lets routers depend on behaviour, not on
how services are wired together.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import HeatAssistantError
from app.core.logging import get_logger
from app.schemas.temperature import TemperatureQuery
from app.services.ai_service import AIService
from app.services.fortyguard_service import FortyGuardService
from app.services.heat_service import HeatAssessment, HeatService

logger = get_logger(__name__)


@lru_cache
def get_fortyguard_service() -> FortyGuardService:
    return FortyGuardService(get_settings())


@lru_cache
def get_heat_service() -> HeatService:
    return HeatService()


@lru_cache
def get_ai_service() -> AIService:
    return AIService(get_settings())


async def get_assessment(query: TemperatureQuery) -> HeatAssessment:
    """Fetch a reading and assess its heat risk. Raises on any failure."""
    reading = await get_fortyguard_service().get_temperature(query)
    return get_heat_service().assess(reading)


async def try_get_assessment(query: TemperatureQuery | None) -> HeatAssessment | None:
    """Best-effort assessment for the AI endpoints.

    Returns ``None`` (instead of raising) when no location was supplied or the
    upstream data could not be retrieved, so AI features can still return
    general guidance with ``data_available=false``.
    """
    if query is None:
        return None
    try:
        return await get_assessment(query)
    except HeatAssistantError as exc:
        logger.info("Proceeding without live data (%s).", exc.code)
        return None


__all__ = [
    "get_fortyguard_service",
    "get_heat_service",
    "get_ai_service",
    "get_assessment",
    "try_get_assessment",
]
