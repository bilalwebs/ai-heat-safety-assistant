"""AI chat endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.services import get_ai_service, try_get_assessment
from app.services.ai_service import DISCLAIMER

router = APIRouter(tags=["AI Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the AI heat-safety assistant a question",
    description=(
        "Answers natural-language questions such as 'Can I go running now?'. "
        "When a location is provided, the assistant grounds its answer in live "
        "FortyGuard data and the computed risk level, clearly separating "
        "measured data from general advice. It never invents temperature values."
    ),
)
async def chat(request: ChatRequest) -> ChatResponse:
    assessment = await try_get_assessment(request.to_query())
    answer, generated_by = await get_ai_service().answer_chat(
        question=request.question,
        assessment=assessment,
        location=request.location,
    )
    return ChatResponse(
        answer=answer,
        location=request.location,
        temperature_celsius=(assessment.reading.temperature_celsius if assessment else None),
        risk_level=(assessment.risk_level if assessment else None),
        data_available=assessment is not None,
        generated_by=generated_by,
        disclaimer=DISCLAIMER,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
