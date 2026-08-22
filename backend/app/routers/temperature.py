"""Temperature endpoint: hyperlocal reading + normalised risk level."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, status

from app.schemas.common import ErrorResponse
from app.schemas.temperature import TemperatureQuery, TemperatureResponse
from app.services import get_assessment

router = APIRouter(tags=["Temperature"])


@router.post(
    "/temperature",
    response_model=TemperatureResponse,
    summary="Get hyperlocal temperature and heat-risk level",
    description=(
        "Fetches a temperature reading from the FortyGuard Temperature API for "
        "the given location, normalises it, and returns a clean, "
        "application-level view including a heat-risk level. Only fields "
        "actually provided by the upstream API are populated."
    ),
    responses={
        502: {"model": ErrorResponse, "description": "Upstream API error"},
        503: {"model": ErrorResponse, "description": "Upstream API unavailable / not configured"},
        504: {"model": ErrorResponse, "description": "Upstream API timeout"},
    },
    status_code=status.HTTP_200_OK,
)
async def get_temperature(query: TemperatureQuery) -> TemperatureResponse:
    assessment = await get_assessment(query)
    reading = assessment.reading
    return TemperatureResponse(
        location=reading.location,
        latitude=reading.latitude,
        longitude=reading.longitude,
        temperature=reading.temperature,
        unit=reading.unit,
        temperature_celsius=reading.temperature_celsius,
        humidity_percent=reading.humidity_percent,
        risk_level=assessment.risk_level,
        risk_level_source=assessment.risk_level_source,
        resolution=reading.resolution,
        measured_at=reading.measured_at,
        source=reading.source,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
