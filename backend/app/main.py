"""FastAPI application factory and wiring.

Responsibilities kept out of the routers live here: app configuration, CORS,
lifespan (resource cleanup), and consistent exception handling. No business
logic is placed in this module.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import HeatAssistantError
from app.core.logging import configure_logging, get_logger
from app.routers import (
    chat,
    health,
    heat_risk,
    heatmap,
    outdoor_plan,
    recommendations,
    temperature,
)
from app.services import get_fortyguard_service

logger = get_logger(__name__)

API_V1 = "/api/v1"

# Starlette renamed this constant; support both old and new versions.
HTTP_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)

DESCRIPTION = """
**AI Heat Safety Assistant** — a heat-safety backend built on the FortyGuard
Temperature API.

* Hyperlocal temperature intelligence (via FortyGuard)
* Heat-risk analysis (official upstream level, or a documented NWS-based calculation)
* AI safety recommendations, an outdoor-activity planner, and a heat-safety chat assistant

All AI features are grounded in verified temperature data and never invent values.
Guidance is general and not medical advice.
"""

TAGS_METADATA = [
    {"name": "System", "description": "Health and readiness checks."},
    {"name": "Temperature", "description": "Hyperlocal temperature readings."},
    {"name": "Heatmap", "description": "FortyGuard heatmap submission and results (U.S. only)."},
    {"name": "Heat Risk", "description": "Heat-risk assessment and safety actions."},
    {"name": "AI Recommendations", "description": "Activity-specific safety recommendations."},
    {"name": "Outdoor Planner", "description": "Safer timing for outdoor activity."},
    {"name": "AI Chat", "description": "Natural-language heat-safety assistant."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Starting %s v%s (env=%s). FortyGuard ready=%s, AI LLM enabled=%s.",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.fortyguard_ready,
        settings.ai_configured,
    )
    if not settings.fortyguard_ready:
        logger.warning(
            "FortyGuard API is not configured; FortyGuard heatmap endpoints "
            "will be unavailable until FORTYGUARD_API_KEY and "
            "FORTYGUARD_BASE_URL are set."
        )
    if not settings.fortyguard_configured:
        logger.info(
            "Legacy single-point temperature endpoint is not configured; "
            "FORTYGUARD_TEMPERATURE_PATH is not set."
        )
    try:
        yield
    finally:
        await get_fortyguard_service().aclose()
        logger.info("Shutdown complete; FortyGuard client closed.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)

    # System
    app.include_router(health.router)
    # Versioned API
    app.include_router(temperature.router, prefix=API_V1)
    app.include_router(heatmap.router, prefix=API_V1)
    app.include_router(heat_risk.router, prefix=API_V1)
    app.include_router(recommendations.router, prefix=API_V1)
    app.include_router(outdoor_plan.router, prefix=API_V1)
    app.include_router(chat.router, prefix=API_V1)

    return app


def _error_payload(code: str, message: str, status_code: int, **extra) -> dict:
    body = {"code": code, "message": message, "status_code": status_code}
    body.update(extra)
    return {"error": body}


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HeatAssistantError)
    async def handle_app_error(request: Request, exc: HeatAssistantError):
        logger.info("Handled %s -> %s", exc.__class__.__name__, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.detail, exc.status_code),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Compact, safe representation of validation problems.
        details = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=HTTP_422,
            content=_error_payload(
                "validation_error",
                "Request validation failed.",
                HTTP_422,
                details=details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Never leak stack traces or secrets to clients.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_error",
                "An unexpected internal error occurred.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
        )


app = create_app()
