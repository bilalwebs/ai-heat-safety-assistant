"""Heat-risk request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel
from app.schemas.temperature import TemperatureQuery


class HeatRiskRequest(TemperatureQuery):
    """Heat-risk input. Inherits the location fields from ``TemperatureQuery``."""


class HeatRiskResponse(BaseModel):
    location: str | None = None
    temperature: float
    unit: str = "°C"
    temperature_celsius: float
    humidity_percent: float | None = None
    heat_index_celsius: float | None = Field(
        default=None,
        description="Apparent temperature (heat index) when humidity is available.",
    )
    risk_level: RiskLevel
    risk_level_source: str = Field(
        ..., description="'fortyguard' if upstream supplied it, else 'calculated'."
    )
    explanation: str = Field(..., description="Plain-language reason for the level.")
    recommended_actions: list[str] = Field(
        default_factory=list, description="General, safety-oriented actions."
    )
    disclaimer: str = Field(
        ...,
        description="Clarifies that guidance is general and not medical advice.",
    )
    measured_at: str | None = None
    timestamp: str
