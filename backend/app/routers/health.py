"""Health / readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    summary="Service health check",
    description=(
        "Lightweight liveness/readiness probe. Reports service status and "
        "non-sensitive readiness flags. Never exposes secrets."
    ),
)
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        # Readiness flags (booleans only — no keys or URLs are exposed).
        "fortyguard_ready": settings.fortyguard_ready,
        "ai_llm_enabled": settings.ai_configured,
    }
