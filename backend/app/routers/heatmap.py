"""Heatmap endpoints — the frontend's door to FortyGuard heatmaps.

The FortyGuard heatmap workflow is asynchronous (submit a job, then poll for
its result). This router hides that behind a bounded, request-scoped wait so a
frontend never has to know about — or call — ``api.fortyguard.com`` directly:

  * ``POST /api/v1/heatmap`` — validate + submit the job, then wait up to a
    short server-side budget. Returns **200** with the result if it finishes in
    time, or **202** + ``activity_id`` + ``poll_url`` if it is still processing.
  * ``GET  /api/v1/heatmap/{activity_id}`` — fetch a previously-submitted job:
    **200** completed, **202** processing, **404** unknown/expired id, **502**
    if the upstream task failed.

FortyGuard coverage is U.S. only; requests for non-U.S. areas will not return
data. Nothing FortyGuard-specific (keys, headers, raw upstream errors) leaks
beyond the single service seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Path, Response, status

from app.core.exceptions import FortyGuardTaskFailedError
from app.schemas.common import ErrorResponse
from app.schemas.heatmap import HeatmapRequest, HeatmapResponse
from app.services import get_fortyguard_service

router = APIRouter(tags=["Heatmap"])

# Kept in sync with the API_V1 prefix in app.main; used only to build the
# client-facing poll URL, never to call FortyGuard.
_POLL_PREFIX = "/api/v1/heatmap"

_UPSTREAM_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Activity id not found / expired"},
    502: {"model": ErrorResponse, "description": "Upstream API error or task failed"},
    503: {"model": ErrorResponse, "description": "Upstream API unavailable / not configured"},
    504: {"model": ErrorResponse, "description": "Upstream API timeout"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _poll_url(activity_id: str) -> str:
    return f"{_POLL_PREFIX}/{activity_id}"


def _processing_response(
    activity_id: str, analytic_type: str, value_key: Optional[str]
) -> HeatmapResponse:
    return HeatmapResponse(
        activity_id=activity_id,
        status="processing",
        ready=False,
        analytic_type=analytic_type,
        value_key=value_key,
        poll_url=_poll_url(activity_id),
        timestamp=_now(),
    )


def _completed_response(
    activity_id: str,
    data: dict[str, Any],
    analytic_type: str,
    fallback_value_key: Optional[str] = None,
) -> HeatmapResponse:
    service = get_fortyguard_service()
    result = service.extract_result(data)
    stats, tile_count = service.extract_stats_and_count(result)
    # Prefer the value key inferred from the real tiles; fall back to the
    # request's analytic-type hint (e.g. when polling a fresh, empty result).
    value_key = service.extract_value_key(result) or fallback_value_key
    return HeatmapResponse(
        activity_id=activity_id,
        status="completed",
        ready=True,
        analytic_type=analytic_type,
        value_key=value_key,
        tile_count=tile_count,
        stats=stats,
        result=result,
        timestamp=_now(),
    )


@router.post(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Submit a FortyGuard heatmap job (U.S. locations only)",
    description=(
        "Validates the request, submits a heatmap job to the FortyGuard API, "
        "and waits briefly for it to finish. Returns **200** with the result if "
        "it completes within the server-side wait budget, otherwise **202** "
        "with an `activity_id` and `poll_url` to fetch it later.\n\n"
        "Area of interest: pass an explicit GeoJSON `polygon_aoi`, or a "
        "`latitude`/`longitude` centre (a small square AOI is built for you). "
        "FortyGuard coverage is U.S. only."
    ),
    responses={
        202: {"model": HeatmapResponse, "description": "Accepted; still processing"},
        **_UPSTREAM_RESPONSES,
    },
    status_code=status.HTTP_200_OK,
)
async def submit_heatmap(request: HeatmapRequest, response: Response) -> HeatmapResponse:
    service = get_fortyguard_service()
    activity_id = await service.submit_heatmap(request.to_payload())
    data = await service.wait_for_activity(activity_id)

    if data is None:
        response.status_code = status.HTTP_202_ACCEPTED
        return _processing_response(
            activity_id, request.analytic_type.value, request.value_key
        )
    return _completed_response(
        activity_id, data, request.analytic_type.value, request.value_key
    )


@router.get(
    "/heatmap/{activity_id}",
    response_model=HeatmapResponse,
    summary="Fetch a previously-submitted heatmap job",
    description=(
        "Fetches the current state of a heatmap job by its `activity_id`. "
        "Returns **200** when complete, **202** while still processing, **404** "
        "if the id is unknown or expired, and **502** if the upstream task "
        "failed."
    ),
    responses={
        202: {"model": HeatmapResponse, "description": "Still processing"},
        **_UPSTREAM_RESPONSES,
    },
    status_code=status.HTTP_200_OK,
)
async def get_heatmap(
    response: Response,
    activity_id: str = Path(..., min_length=1, description="FortyGuard activity id."),
) -> HeatmapResponse:
    service = get_fortyguard_service()
    data = await service.fetch_activity(activity_id)
    state = service.classify_status(data)

    # The status endpoint does not echo analytic_type; report it only if the
    # upstream ever includes it, otherwise "unknown". value_key for a completed
    # job is inferred from the actual tiles inside _completed_response.
    analytic_type = _upstream_analytic_type(data)

    if state == "failed":
        raise FortyGuardTaskFailedError()
    if state == "processing":
        response.status_code = status.HTTP_202_ACCEPTED
        return _processing_response(activity_id, analytic_type, None)
    return _completed_response(activity_id, data, analytic_type)


def _upstream_analytic_type(data: dict[str, Any]) -> str:
    """Read analytic_type from the status object or its nested result/stats.

    A live status object does not include it, so this returns "unknown" in the
    common case; it exists only to surface the value if the upstream ever adds
    it, rather than to guess.
    """
    if isinstance(data, dict):
        if data.get("analytic_type"):
            return str(data["analytic_type"])
        result = data.get("result")
        if isinstance(result, dict):
            if result.get("analytic_type"):
                return str(result["analytic_type"])
            stats = result.get("stats_data")
            if isinstance(stats, dict) and stats.get("analytic_type"):
                return str(stats["analytic_type"])
    return "unknown"
