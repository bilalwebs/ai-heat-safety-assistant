"""Temperature request/response and internal normalised schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import RiskLevel


class LocationInput(BaseModel):
    """Reusable location fields with light validation.

    Latitude/longitude must be supplied together, but this base does not
    require any location at all — endpoints that can operate without one
    (recommendations, outdoor plan) build on this directly.
    """

    location: Optional[str] = Field(
        default=None,
        description="Free-text location, e.g. 'Karachi, Pakistan'.",
        examples=["Karachi, Pakistan"],
    )
    latitude: Optional[float] = Field(
        default=None, ge=-90, le=90, description="Latitude in decimal degrees."
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180, le=180, description="Longitude in decimal degrees."
    )

    @model_validator(mode="after")
    def _coords_paired(self) -> "LocationInput":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("'latitude' and 'longitude' must be provided together.")
        return self

    @property
    def has_location_signal(self) -> bool:
        has_coords = self.latitude is not None and self.longitude is not None
        return bool((self.location and self.location.strip()) or has_coords)

    def to_query(self) -> Optional["TemperatureQuery"]:
        """Return a strict ``TemperatureQuery`` if a signal is present, else None."""
        if not self.has_location_signal:
            return None
        return TemperatureQuery(
            location=self.location,
            latitude=self.latitude,
            longitude=self.longitude,
        )


class TemperatureQuery(LocationInput):
    """Location input that *requires* a usable location signal."""

    @model_validator(mode="after")
    def _require_location_signal(self) -> "TemperatureQuery":
        if not self.has_location_signal:
            raise ValueError(
                "Provide either 'location' or both 'latitude' and 'longitude'."
            )
        return self


class NormalizedTemperature(BaseModel):
    """Internal, provider-agnostic temperature reading.

    This is our own schema. The FortyGuard adapter maps the vendor response
    into this shape; only fields actually present upstream are populated.
    """

    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    temperature: float = Field(..., description="Temperature in the reported unit.")
    unit: str = Field(default="°C", description="Unit label of 'temperature'.")
    temperature_celsius: float = Field(
        ..., description="Temperature converted to Celsius for internal calculations."
    )
    humidity_percent: Optional[float] = Field(default=None, ge=0, le=100)
    official_risk_level: Optional[str] = Field(
        default=None,
        description="Risk/category value if the upstream API supplies one.",
    )
    resolution: Optional[str] = Field(
        default=None, description="Spatial resolution/precision if reported."
    )
    measured_at: Optional[str] = Field(
        default=None, description="Upstream measurement timestamp if reported."
    )
    source: str = Field(default="fortyguard", description="Data source identifier.")


class TemperatureResponse(BaseModel):
    """Clean application-level temperature response."""

    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    temperature: float
    unit: str = "°C"
    temperature_celsius: float
    humidity_percent: Optional[float] = None
    risk_level: RiskLevel = Field(
        ..., description="Normalised heat-risk level for this reading."
    )
    risk_level_source: str = Field(
        ..., description="'fortyguard' if upstream supplied it, else 'calculated'."
    )
    resolution: Optional[str] = None
    measured_at: Optional[str] = None
    source: str = "fortyguard"
    timestamp: str = Field(..., description="Server response time (ISO 8601, UTC).")
