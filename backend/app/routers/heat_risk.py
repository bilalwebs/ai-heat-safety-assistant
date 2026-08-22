"""Heat-risk endpoint: risk level, explanation and recommended actions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.common import ErrorResponse
from app.schemas.heat_risk import HeatRiskRequest, HeatRiskResponse
from app.services import get_assessment

router = APIRouter(tags=["Heat Risk"])


@router.post(
    "/heat-risk",
    response_model=HeatRiskResponse,
    summary="Assess heat risk for a location",
    description=(
        "Processes FortyGuard temperature/heat data into a heat-risk "
        "assessment. If FortyGuard supplies an official risk level it is used "
        "directly; otherwise the level is calculated from temperature using "
        "the documented US NWS Heat Index categories. Guidance is general and "
        "not medical advice."
    ),
    responses={
        502: {"model": ErrorResponse, "description": "Upstream API error"},
        503: {"model": ErrorResponse, "description": "Upstream API unavailable / not configured"},
        504: {"model": ErrorResponse, "description": "Upstream API timeout"},
    },
)
async def assess_heat_risk(request: HeatRiskRequest) -> HeatRiskResponse:
    assessment = await get_assessment(request)
    reading = assessment.reading
    return HeatRiskResponse(
        location=reading.location,
        temperature=reading.temperature,
        unit=reading.unit,
        temperature_celsius=reading.temperature_celsius,
        humidity_percent=reading.humidity_percent,
        heat_index_celsius=assessment.heat_index_celsius,
        risk_level=assessment.risk_level,
        risk_level_source=assessment.risk_level_source,
        explanation=assessment.explanation,
        recommended_actions=assessment.recommended_actions,
        disclaimer=assessment.disclaimer,
        measured_at=reading.measured_at,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
