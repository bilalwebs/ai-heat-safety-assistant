"""Tests for the FortyGuard heatmap service and endpoints.

All external HTTP is mocked with ``httpx.MockTransport`` — no test calls the
real FortyGuard API. The async submit->poll workflow is driven with tiny poll
intervals/budgets so the suite stays fast.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.routers.heatmap as heatmap_router
from app.core.exceptions import (
    FortyGuardActivityNotFoundError,
    FortyGuardNotConfiguredError,
    FortyGuardResponseError,
    FortyGuardTaskFailedError,
    FortyGuardTimeoutError,
    FortyGuardUnavailableError,
    FortyGuardUpstreamError,
)
from app.main import app
from app.schemas.heatmap import HeatmapRequest
from app.services.fortyguard_service import FortyGuardService
from tests.conftest import make_settings, transport_raising

# FortyGuard is U.S.-only; San Jose is the sanctioned test location.
SAN_JOSE = {"latitude": 37.3382, "longitude": -121.8863}
TCM_BODY = {**SAN_JOSE, "start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1}

# A realistic completed status object (shapes confirmed against a live San Jose
# tcm response): status is capitalised; tcm tiles carry min/average/max_
# temperature + tile_id; stats_data is nested; the result nests map_data +
# stats_data.
COMPLETED_INNER = {
    "activity_id": "act-123",
    "status": "Completed",
    "result": {
        "stats_data": {
            "temperature_stats": {"min": 29.8, "max": 31.9, "mean": 30.75},
            "temperature_frequency": {},
        },
        "map_data": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "min_temperature": 29.8,
                        "average_temperature": 30.1,
                        "max_temperature": 30.5,
                        "tile_id": "a",
                    },
                },
                {
                    "type": "Feature",
                    "properties": {
                        "min_temperature": 31.0,
                        "average_temperature": 31.4,
                        "max_temperature": 31.9,
                        "tile_id": "b",
                    },
                },
            ],
        },
    },
}


# ----- helpers ---------------------------------------------------------


def fast_settings(**overrides):
    """Heatmap-ready settings with instant polling for tests."""
    base = {
        "fortyguard_api_key": "test-key-1234",
        "fortyguard_base_url": "https://api.fortyguard.test",
        "fortyguard_poll_interval_seconds": 0.0,
        "fortyguard_max_wait_seconds": 2.0,
    }
    base.update(overrides)
    return make_settings(**base)


def routing_service(handler, **settings_overrides) -> FortyGuardService:
    settings = fast_settings(**settings_overrides)
    return FortyGuardService(settings, transport=httpx.MockTransport(handler))


def _submit_ok(activity_id: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/heatmap":
            return httpx.Response(200, json={"data": {"activity_id": activity_id}})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    return handler


# ----- schema validation ----------------------------------------------


def test_request_builds_verified_tcm_payload():
    req = HeatmapRequest(**TCM_BODY, analytic_type="tcm", granularity=100)
    payload = req.to_payload()
    assert payload["analytic_type"] == "tcm"
    assert payload["granularity"] == 100
    poly = payload["polygon_aoi"]
    assert poly["type"] == "Polygon"
    ring = poly["coordinates"][0]
    assert ring[0] == ring[-1]  # closed ring
    assert payload["date_time"] == {
        "start_date": "2024-07-15",
        "filter_type": 1,
        "start_time": "14:00",
    }
    assert req.value_key == "average_temperature"
    assert "threshold" not in payload


def test_request_exceedance_requires_threshold_and_direction():
    with pytest.raises(ValidationError):
        HeatmapRequest(**SAN_JOSE, start_date="2024-07-15", filter_type=3, analytic_type="exceedance")


def test_request_exceedance_payload_uses_value_key():
    req = HeatmapRequest(
        **SAN_JOSE,
        start_date="2024-07-15",
        filter_type=3,
        analytic_type="exceedance",
        threshold=35.0,
        direction="above",
    )
    assert req.value_key == "value"
    payload = req.to_payload()
    assert payload["threshold"] == 35.0
    assert payload["direction"] == "above"


def test_request_filter2_requires_end_time():
    with pytest.raises(ValidationError):
        HeatmapRequest(**SAN_JOSE, start_date="2024-07-15", start_time="10:00", filter_type=2)


def test_request_rejects_invalid_granularity():
    with pytest.raises(ValidationError):
        HeatmapRequest(**TCM_BODY, granularity=50)


def test_request_requires_an_area_of_interest():
    with pytest.raises(ValidationError):
        HeatmapRequest(start_date="2024-07-15", start_time="10:00", filter_type=1)


def test_request_accepts_explicit_polygon():
    poly = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    req = HeatmapRequest(polygon_aoi=poly, start_date="2024-07-15", filter_type=3)
    # Pydantic copies dict inputs, so compare by value (not identity).
    assert req.to_payload()["polygon_aoi"] == poly


# ----- service: submit -------------------------------------------------


async def test_submit_returns_activity_id():
    svc = routing_service(_submit_ok("act-1"))
    assert await svc.submit_heatmap({"any": "payload"}) == "act-1"
    await svc.aclose()


async def test_submit_not_configured_raises():
    svc = FortyGuardService(
        make_settings(fortyguard_api_key=None),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    with pytest.raises(FortyGuardNotConfiguredError):
        await svc.submit_heatmap({})


async def test_submit_missing_activity_id_is_bad_response():
    svc = routing_service(lambda r: httpx.Response(200, json={"data": {}}))
    with pytest.raises(FortyGuardResponseError):
        await svc.submit_heatmap({})
    await svc.aclose()


async def test_submit_error_field_maps_to_upstream_error():
    svc = routing_service(lambda r: httpx.Response(200, json={"error": True, "message": "bad aoi"}))
    with pytest.raises(FortyGuardUpstreamError):
        await svc.submit_heatmap({})
    await svc.aclose()


async def test_submit_401_maps_to_upstream_error():
    svc = routing_service(lambda r: httpx.Response(401, json={"detail": "nope"}))
    with pytest.raises(FortyGuardUpstreamError):
        await svc.submit_heatmap({})
    await svc.aclose()


async def test_submit_timeout_maps_to_timeout_error():
    svc = FortyGuardService(
        fast_settings(),
        transport=transport_raising(lambda req: httpx.ReadTimeout("t", request=req)),
    )
    with pytest.raises(FortyGuardTimeoutError):
        await svc.submit_heatmap({})
    await svc.aclose()


async def test_submit_connection_error_maps_to_unavailable():
    svc = FortyGuardService(
        fast_settings(),
        transport=transport_raising(lambda req: httpx.ConnectError("no route", request=req)),
    )
    with pytest.raises(FortyGuardUnavailableError):
        await svc.submit_heatmap({})
    await svc.aclose()


# ----- service: poll / wait --------------------------------------------


async def test_wait_returns_completed_result():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-123"}})
        return httpx.Response(200, json={"data": COMPLETED_INNER})

    svc = routing_service(handler)
    activity_id = await svc.submit_heatmap({})
    data = await svc.wait_for_activity(activity_id)
    assert data is not None
    assert svc.classify_status(data) == "completed"
    stats, count = svc.extract_stats_and_count(svc.extract_result(data))
    assert count == 2
    assert "temperature_stats" in stats
    assert svc.extract_value_key(svc.extract_result(data)) == "average_temperature"
    await svc.aclose()


async def test_wait_failed_status_raises_task_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-9"}})
        return httpx.Response(200, json={"data": {"status": "failed"}})

    svc = routing_service(handler)
    activity_id = await svc.submit_heatmap({})
    with pytest.raises(FortyGuardTaskFailedError):
        await svc.wait_for_activity(activity_id)
    await svc.aclose()


async def test_wait_budget_exceeded_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-1"}})
        return httpx.Response(200, json={"data": {"status": "processing"}})

    svc = routing_service(handler, fortyguard_max_wait_seconds=0.0)
    activity_id = await svc.submit_heatmap({})
    assert await svc.wait_for_activity(activity_id) is None
    await svc.aclose()


async def test_wait_polls_past_404_until_completed():
    calls = {"status": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-2"}})
        calls["status"] += 1
        if calls["status"] == 1:
            return httpx.Response(404, json={})  # not visible yet
        return httpx.Response(200, json={"data": {"status": "completed", "result": {}}})

    svc = routing_service(handler)
    activity_id = await svc.submit_heatmap({})
    data = await svc.wait_for_activity(activity_id)
    assert data is not None and svc.classify_status(data) == "completed"
    assert calls["status"] >= 2
    await svc.aclose()


async def test_fetch_activity_unknown_id_is_not_found():
    svc = routing_service(lambda r: httpx.Response(404, json={}))
    with pytest.raises(FortyGuardActivityNotFoundError):
        await svc.fetch_activity("nope")
    await svc.aclose()


# ----- endpoints -------------------------------------------------------


def test_post_heatmap_completed_200(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-77"}})
        return httpx.Response(200, json={"data": COMPLETED_INNER})

    svc = routing_service(handler)
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/heatmap", json={**TCM_BODY, "analytic_type": "tcm"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["status"] == "completed"
    assert body["activity_id"] == "act-77"
    assert body["value_key"] == "average_temperature"
    assert body["tile_count"] == 2
    assert body["coverage_note"] and body["disclaimer"]
    # The API key must never appear in a response.
    assert "test-key-1234" not in resp.text


def test_post_heatmap_processing_202(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"activity_id": "act-88"}})
        return httpx.Response(200, json={"data": {"status": "processing"}})

    svc = routing_service(handler, fortyguard_max_wait_seconds=0.0)
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/heatmap", json=TCM_BODY)
    assert resp.status_code == 202
    body = resp.json()
    assert body["ready"] is False
    assert body["status"] == "processing"
    assert body["activity_id"] == "act-88"
    assert body["poll_url"].endswith("/api/v1/heatmap/act-88")


def test_post_heatmap_validation_422():
    with TestClient(app) as client:
        # filter_type defaults to 1 which requires start_time; also no AOI.
        resp = client.post("/api/v1/heatmap", json={"start_date": "2024-07-15"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_post_heatmap_503_when_not_configured(monkeypatch):
    svc = FortyGuardService(
        make_settings(fortyguard_api_key=None),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/heatmap", json=TCM_BODY)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "fortyguard_not_configured"


def test_get_heatmap_completed_200(monkeypatch):
    svc = routing_service(lambda r: httpx.Response(200, json={"data": COMPLETED_INNER}))
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.get("/api/v1/heatmap/act-123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["tile_count"] == 2
    assert body["value_key"] == "average_temperature"  # inferred from real tiles


def test_get_heatmap_processing_202(monkeypatch):
    svc = routing_service(
        lambda r: httpx.Response(200, json={"data": {"status": "processing", "analytic_type": "tcm"}})
    )
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.get("/api/v1/heatmap/act-x")
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"


def test_get_heatmap_not_found_404(monkeypatch):
    svc = routing_service(lambda r: httpx.Response(404, json={}))
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.get("/api/v1/heatmap/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "activity_not_found"


def test_get_heatmap_failed_502(monkeypatch):
    svc = routing_service(lambda r: httpx.Response(200, json={"data": {"status": "failed"}}))
    monkeypatch.setattr(heatmap_router, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.get("/api/v1/heatmap/act-f")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "fortyguard_task_failed"
