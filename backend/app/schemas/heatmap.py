"""Heatmap request/response schemas for the FortyGuard integration.

The request maps 1:1 onto the verified FortyGuard ``POST /v1/heatmap`` body
(``polygon_aoi``, ``date_time``, ``granularity``, ``analytic_type`` and, for
analysis types, ``threshold``/``direction``). Validation enforces the
documented ``filter_type`` and ``analytic_type`` matrices so we never send a
malformed request shape.

Building a small square AOI from a centre point + radius is *our* convenience
(clearly documented), not a FortyGuard feature. Callers may instead pass an
explicit GeoJSON ``polygon_aoi``.

NOTE: FortyGuard coverage is U.S. only. Examples use San Jose, California.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Tile value properties (confirmed against a live San Jose tcm response):
# tcm tiles carry min_temperature / average_temperature / max_temperature /
# tile_id. FortyGuard documents threshold analyses (exceedance/persistence) as
# carrying a single `value` property (documented, not live-verified here). The
# full, untransformed tiles are always returned under `result.map_data`.
COVERAGE_NOTE = (
    "FortyGuard coverage is U.S. only — locations must be inside the United "
    "States and dates from 2021 to the present."
)
DISCLAIMER = (
    "Heatmap values are model-derived environmental data from FortyGuard for "
    "U.S. locations. Use as general guidance, not a substitute for official "
    "heat warnings; not medical advice."
)

_ANALYSIS_MIN_YEAR = 2021


class AnalyticType(str, Enum):
    TCM = "tcm"  # snapshot temperature
    TIME_OF_MEASURE = "time_of_measure"  # UTC hour of peak
    EXCEEDANCE = "exceedance"  # hours above/below a threshold
    PERSISTENCE = "persistence"  # longest continuous period above/below


class Direction(str, Enum):
    ABOVE = "above"
    BELOW = "below"


_ANALYSIS_TYPES = {AnalyticType.EXCEEDANCE, AnalyticType.PERSISTENCE}


def _check_date(value: str, field: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"'{field}' must be a date in YYYY-MM-DD format.") from exc
    if parsed.year < _ANALYSIS_MIN_YEAR:
        raise ValueError(
            f"'{field}' is before FortyGuard coverage (data starts {_ANALYSIS_MIN_YEAR})."
        )


def _check_time(value: str, field: str) -> None:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"'{field}' must be a time in 24h HH:MM format.") from exc


class HeatmapRequest(BaseModel):
    """Input for a FortyGuard heatmap submission."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "latitude": 37.3382,
                    "longitude": -121.8863,
                    "radius_km": 1.0,
                    "start_date": "2024-07-15",
                    "start_time": "14:00",
                    "filter_type": 1,
                    "analytic_type": "tcm",
                    "granularity": 100,
                }
            ]
        }
    )

    # --- Area of interest: an explicit polygon OR a centre point ----------
    polygon_aoi: Optional[dict[str, Any]] = Field(
        default=None,
        description="Explicit GeoJSON Polygon. If omitted, provide latitude+longitude.",
    )
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(
        default=1.0,
        gt=0,
        le=50,
        description="Half-size of the square AOI built around a centre point (km).",
    )

    # --- Date / time window (shape depends on filter_type) ----------------
    start_date: str = Field(..., description="YYYY-MM-DD.", examples=["2024-07-15"])
    start_time: Optional[str] = Field(default=None, description="HH:MM (24h).", examples=["14:00"])
    end_time: Optional[str] = Field(default=None, description="HH:MM (24h).")
    end_date: Optional[str] = Field(default=None, description="YYYY-MM-DD.")
    filter_type: int = Field(
        default=1,
        description="1=single hour, 2=hour range (same day), 3=single day, 4=day range.",
    )

    # --- Analysis ---------------------------------------------------------
    granularity: int = Field(default=100, description="Tile size: 60, 80 or 100.")
    analytic_type: AnalyticType = Field(default=AnalyticType.TCM)
    threshold: Optional[float] = Field(
        default=None, description="Celsius threshold (required for exceedance/persistence)."
    )
    direction: Optional[Direction] = Field(
        default=None, description="'above' or 'below' (required for exceedance/persistence)."
    )

    # --- Validation -------------------------------------------------------
    @model_validator(mode="after")
    def _validate(self) -> "HeatmapRequest":
        self._validate_aoi()
        self._validate_enums()
        self._validate_time_matrix()
        self._validate_analytic_matrix()
        return self

    def _validate_aoi(self) -> None:
        has_point = self.latitude is not None or self.longitude is not None
        if self.polygon_aoi is not None:
            poly = self.polygon_aoi
            if not isinstance(poly, dict) or poly.get("type") != "Polygon":
                raise ValueError("'polygon_aoi' must be a GeoJSON object with type 'Polygon'.")
            coords = poly.get("coordinates")
            if not isinstance(coords, list) or not coords:
                raise ValueError("'polygon_aoi.coordinates' must be a non-empty list.")
            return
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("'latitude' and 'longitude' must be provided together.")
        if not has_point:
            raise ValueError(
                "Provide either 'polygon_aoi' or both 'latitude' and 'longitude'."
            )

    def _validate_enums(self) -> None:
        if self.granularity not in (60, 80, 100):
            raise ValueError("'granularity' must be one of 60, 80 or 100.")
        if self.filter_type not in (1, 2, 3, 4):
            raise ValueError("'filter_type' must be one of 1, 2, 3 or 4.")

    def _validate_time_matrix(self) -> None:
        _check_date(self.start_date, "start_date")
        if self.filter_type in (1, 2):
            if not self.start_time:
                raise ValueError(f"filter_type={self.filter_type} requires 'start_time'.")
            _check_time(self.start_time, "start_time")
        if self.filter_type == 2:
            if not self.end_time:
                raise ValueError("filter_type=2 requires 'end_time'.")
            _check_time(self.end_time, "end_time")
        if self.filter_type == 4:
            if not self.end_date:
                raise ValueError("filter_type=4 requires 'end_date'.")
            _check_date(self.end_date, "end_date")

    def _validate_analytic_matrix(self) -> None:
        if self.analytic_type in _ANALYSIS_TYPES:
            if self.threshold is None or self.direction is None:
                raise ValueError(
                    f"analytic_type='{self.analytic_type.value}' requires "
                    "'threshold' (Celsius) and 'direction' ('above'/'below')."
                )

    # --- Transform to the verified FortyGuard body ------------------------
    @property
    def value_key(self) -> Optional[str]:
        """Primary tile property to colour a map by, for this analytic type.

        Live-verified for ``tcm`` (tiles carry min/average/max_temperature; we
        treat ``average_temperature`` as primary). ``exceedance``/``persistence``
        use ``value`` per the FortyGuard docs (not live-verified here).
        Returns ``None`` when the property name is unknown for the type.

        This is only a hint — the full untransformed tiles are always in
        ``result.map_data`` so a client can read any property it wants.
        """
        if self.analytic_type == AnalyticType.TCM:
            return "average_temperature"
        if self.analytic_type in _ANALYSIS_TYPES:
            return "value"
        return None

    def to_polygon(self) -> dict[str, Any]:
        """Return the explicit polygon, or build a square AOI from the centre.

        GeoJSON uses [longitude, latitude] order. The square is our own
        convenience construction around the point, not a FortyGuard feature.
        """
        if self.polygon_aoi is not None:
            return self.polygon_aoi
        lat = float(self.latitude)  # validated present
        lon = float(self.longitude)
        dlat = self.radius_km / 111.0
        dlon = self.radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
        ring = [
            [lon - dlon, lat - dlat],
            [lon + dlon, lat - dlat],
            [lon + dlon, lat + dlat],
            [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat],
        ]
        return {"type": "Polygon", "coordinates": [ring]}

    def to_date_time(self) -> dict[str, Any]:
        dt: dict[str, Any] = {"start_date": self.start_date, "filter_type": self.filter_type}
        if self.filter_type in (1, 2):
            dt["start_time"] = self.start_time
        if self.filter_type == 2:
            dt["end_time"] = self.end_time
        if self.filter_type == 4:
            dt["end_date"] = self.end_date
        return dt

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "polygon_aoi": self.to_polygon(),
            "date_time": self.to_date_time(),
            "granularity": self.granularity,
            "analytic_type": self.analytic_type.value,
        }
        if self.analytic_type in _ANALYSIS_TYPES:
            payload["threshold"] = self.threshold
            payload["direction"] = self.direction.value if self.direction else None
        return payload


class HeatmapResponse(BaseModel):
    """Clean application-level heatmap response (submit + poll result)."""

    activity_id: str = Field(..., description="FortyGuard async activity identifier.")
    status: str = Field(..., description="submitted | processing | completed | failed.")
    ready: bool = Field(..., description="True when the result is available.")
    analytic_type: str
    value_key: Optional[str] = Field(
        default=None,
        description=(
            "Primary tile property to map by. For tcm this is "
            "'average_temperature' (tiles also carry min_temperature, "
            "max_temperature, tile_id); for exceedance/persistence, 'value'. "
            "Read the full tiles from result.map_data."
        ),
    )
    tile_count: Optional[int] = Field(
        default=None, description="Number of GeoJSON features, if available."
    )
    stats: Optional[dict[str, Any]] = Field(
        default=None, description="Upstream stats_data pass-through, if provided."
    )
    result: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full upstream result (map_data GeoJSON + stats_data) when ready.",
    )
    poll_url: Optional[str] = Field(
        default=None, description="Relative URL to poll for the result when not ready."
    )
    coverage_note: str = COVERAGE_NOTE
    disclaimer: str = DISCLAIMER
    timestamp: str = Field(..., description="Server response time (ISO 8601, UTC).")
