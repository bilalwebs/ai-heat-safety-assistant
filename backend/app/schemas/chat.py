"""AI chat request/response schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import RiskLevel
from app.schemas.temperature import TemperatureQuery


class ChatRequest(BaseModel):
    """Chat input.

    ``location`` (or a coordinate pair) is optional but, when present, lets
    the assistant ground its answer in live heat data. The assistant never
    invents temperature values.
    """

    question: str = Field(
        ..., min_length=1, max_length=2000, examples=["Can I go running now?"]
    )
    location: Optional[str] = Field(default=None, examples=["Karachi, Pakistan"])
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _coords_paired(self) -> "ChatRequest":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("'latitude' and 'longitude' must be provided together.")
        return self

    def to_query(self) -> Optional[TemperatureQuery]:
        has_coords = self.latitude is not None and self.longitude is not None
        if not ((self.location and self.location.strip()) or has_coords):
            return None
        return TemperatureQuery(
            location=self.location, latitude=self.latitude, longitude=self.longitude
        )


class ChatResponse(BaseModel):
    answer: str
    location: Optional[str] = None
    temperature_celsius: Optional[float] = None
    risk_level: Optional[RiskLevel] = None
    data_available: bool = Field(
        ..., description="Whether live temperature data backed this answer."
    )
    generated_by: str = Field(..., description="'llm' or 'rule_based'.")
    disclaimer: str
    timestamp: str
