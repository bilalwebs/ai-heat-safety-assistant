"""Outdoor activity planner request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel
from app.schemas.recommendations import Activity
from app.schemas.temperature import LocationInput


class OutdoorPlanRequest(LocationInput):
    """Outdoor planner input. Optional location fields inherited from ``LocationInput``."""

    activity: Activity = Field(default=Activity.GENERAL)


class OutdoorPlanResponse(BaseModel):
    location: str | None = None
    activity: Activity
    temperature_celsius: float | None = None
    risk_level: RiskLevel
    recommended_window: str = Field(
        ..., description="Safer period for the activity based on available data."
    )
    avoid_window: str | None = Field(
        default=None, description="Period to avoid if determinable."
    )
    explanation: str
    is_forecast: bool = Field(
        ...,
        description=(
            "True only if backed by real forecast data. When false the "
            "guidance reflects current conditions plus general daily heat "
            "patterns, not a temperature forecast."
        ),
    )
    data_available: bool
    disclaimer: str
    timestamp: str
