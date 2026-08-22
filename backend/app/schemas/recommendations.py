"""AI recommendation request/response schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel
from app.schemas.temperature import LocationInput


class Activity(str, Enum):
    WALKING = "walking"
    RUNNING = "running"
    OUTDOOR_WORK = "outdoor_work"
    COMMUTING = "commuting"
    GENERAL = "general"


class RecommendationRequest(LocationInput):
    """Recommendation input.

    Location fields are inherited and optional. If a location signal is
    supplied the server fetches live heat data and grounds the advice in it;
    otherwise general guidance is returned with ``data_available=false``.
    Callers may optionally pass extra free-text ``user_context``.
    """

    activity: Activity = Field(default=Activity.GENERAL)
    user_context: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional extra context, e.g. 'elderly, 45 min commute'.",
    )


class RecommendationResponse(BaseModel):
    location: str | None = None
    activity: Activity
    temperature_celsius: float | None = None
    risk_level: RiskLevel
    recommendations: list[str]
    summary: str
    data_available: bool = Field(
        ..., description="Whether live temperature data backed this response."
    )
    generated_by: str = Field(
        ..., description="'llm' or 'rule_based' — how the text was produced."
    )
    disclaimer: str
    timestamp: str
