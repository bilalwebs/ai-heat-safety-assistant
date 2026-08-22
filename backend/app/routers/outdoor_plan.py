"""Outdoor activity planner endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.common import RiskLevel
from app.schemas.outdoor_plan import OutdoorPlanRequest, OutdoorPlanResponse
from app.services import get_ai_service, try_get_assessment
from app.services.ai_service import DISCLAIMER

router = APIRouter(tags=["Outdoor Planner"])


@router.post(
    "/outdoor-plan",
    response_model=OutdoorPlanResponse,
    summary="Suggest safer timing for an outdoor activity",
    description=(
        "Recommends when outdoor activity is safer based on available data. "
        "This is NOT a temperature forecast: unless the upstream API provides "
        "forecast data, guidance reflects current conditions plus general "
        "daily heat patterns (is_forecast=false)."
    ),
)
async def outdoor_plan(request: OutdoorPlanRequest) -> OutdoorPlanResponse:
    assessment = await try_get_assessment(request.to_query())
    window, avoid, explanation = get_ai_service().plan(
        activity=request.activity,
        assessment=assessment,
        location=request.location,
    )
    return OutdoorPlanResponse(
        location=request.location,
        activity=request.activity,
        temperature_celsius=(assessment.reading.temperature_celsius if assessment else None),
        risk_level=(assessment.risk_level if assessment else RiskLevel.UNKNOWN),
        recommended_window=window,
        avoid_window=avoid,
        explanation=explanation,
        # No forecast source is integrated; this is explicitly current-condition guidance.
        is_forecast=False,
        data_available=assessment is not None,
        disclaimer=DISCLAIMER,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
