"""AI recommendations endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.common import RiskLevel
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse
from app.services import get_ai_service, try_get_assessment
from app.services.ai_service import DISCLAIMER

router = APIRouter(tags=["AI Recommendations"])


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="Generate practical, data-grounded heat-safety recommendations",
    description=(
        "Produces recommendations for a given activity. When a location is "
        "supplied, live FortyGuard data and the computed risk level ground the "
        "advice. The AI never invents temperature values; if live data is "
        "unavailable, general guidance is returned with data_available=false."
    ),
)
async def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    assessment = await try_get_assessment(request.to_query())
    recs, summary, generated_by = await get_ai_service().recommend(
        activity=request.activity,
        assessment=assessment,
        location=request.location,
        user_context=request.user_context,
    )
    return RecommendationResponse(
        location=request.location,
        activity=request.activity,
        temperature_celsius=(assessment.reading.temperature_celsius if assessment else None),
        risk_level=(assessment.risk_level if assessment else RiskLevel.UNKNOWN),
        recommendations=recs,
        summary=summary,
        data_available=assessment is not None,
        generated_by=generated_by,
        disclaimer=DISCLAIMER,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
