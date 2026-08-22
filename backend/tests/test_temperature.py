"""Tests for the temperature service and endpoint (all HTTP mocked)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import app.services as services_module
from app.core.exceptions import (
    FortyGuardNotConfiguredError,
    FortyGuardResponseError,
    FortyGuardTimeoutError,
    FortyGuardUnavailableError,
    FortyGuardUpstreamError,
    LocationNotFoundError,
)
from app.main import app
from app.schemas.temperature import TemperatureQuery
from tests.conftest import make_service, make_settings, transport_raising

SAMPLE_PAYLOAD = {
    "location": "Karachi, Pakistan",
    "temperature": 38.5,
    "unit": "C",
    "humidity": 55,
    "resolution": "2m",
    "measured_at": "2026-08-22T10:00:00Z",
}


# ----- request validation (via API) -----------------------------------


def test_temperature_requires_location():
    with TestClient(app) as client:
        resp = client.post("/api/v1/temperature", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_temperature_rejects_unpaired_coordinates():
    with TestClient(app) as client:
        resp = client.post("/api/v1/temperature", json={"latitude": 24.86})
    assert resp.status_code == 422


# ----- FortyGuard service: success + normalisation ---------------------


async def test_service_normalizes_success_response():
    svc = make_service(SAMPLE_PAYLOAD)
    reading = await svc.get_temperature(TemperatureQuery(location="Karachi, Pakistan"))
    assert reading.temperature == 38.5
    assert reading.temperature_celsius == 38.5
    assert reading.unit == "°C"
    assert reading.humidity_percent == 55
    assert reading.resolution == "2m"
    assert reading.source == "fortyguard"
    await svc.aclose()


async def test_service_converts_fahrenheit_to_celsius():
    svc = make_service({"temp": 100, "unit": "F"})
    reading = await svc.get_temperature(TemperatureQuery(location="Phoenix"))
    assert reading.unit == "°F"
    assert reading.temperature == 100
    assert reading.temperature_celsius == pytest.approx(37.78, abs=0.1)
    await svc.aclose()


async def test_service_reads_nested_and_official_risk():
    payload = {"data": {"reading": {"temperature": 30}, "risk_level": "high"}}
    svc = make_service(payload)
    reading = await svc.get_temperature(TemperatureQuery(location="X"))
    assert reading.temperature == 30
    assert reading.official_risk_level == "high"
    await svc.aclose()


# ----- FortyGuard service: error handling ------------------------------


async def test_service_not_configured_raises():
    settings = make_settings(fortyguard_api_key=None)
    svc = make_service(settings=settings, payload={})
    assert svc.is_configured is False
    with pytest.raises(FortyGuardNotConfiguredError):
        await svc.get_temperature(TemperatureQuery(location="X"))


async def test_service_timeout_maps_to_timeout_error():
    svc = make_service(
        transport=transport_raising(lambda req: httpx.ConnectTimeout("timed out", request=req))
    )
    with pytest.raises(FortyGuardTimeoutError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


async def test_service_connection_error_maps_to_unavailable():
    svc = make_service(
        transport=transport_raising(lambda req: httpx.ConnectError("no route", request=req))
    )
    with pytest.raises(FortyGuardUnavailableError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


async def test_service_404_maps_to_location_not_found():
    svc = make_service({"detail": "nope"}, status_code=404)
    with pytest.raises(LocationNotFoundError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


async def test_service_4xx_maps_to_upstream_error():
    svc = make_service({"detail": "bad"}, status_code=400)
    with pytest.raises(FortyGuardUpstreamError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


async def test_service_5xx_maps_to_unavailable():
    svc = make_service({"detail": "boom"}, status_code=502)
    with pytest.raises(FortyGuardUnavailableError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


async def test_service_missing_temperature_raises_bad_response():
    svc = make_service({"humidity": 50})
    with pytest.raises(FortyGuardResponseError):
        await svc.get_temperature(TemperatureQuery(location="X"))
    await svc.aclose()


# ----- full endpoint happy path (upstream mocked) ----------------------


def test_temperature_endpoint_success(monkeypatch):
    svc = make_service(SAMPLE_PAYLOAD)
    monkeypatch.setattr(services_module, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/temperature", json={"location": "Karachi, Pakistan"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["temperature_celsius"] == 38.5
    assert body["risk_level"] in {"low", "moderate", "high", "very_high", "extreme"}
    assert body["risk_level_source"] == "calculated"
    assert body["timestamp"]
    # The API key must never appear in the response.
    assert "test-key-1234" not in resp.text


def test_temperature_endpoint_503_when_not_configured(monkeypatch):
    svc = make_service(settings=make_settings(fortyguard_api_key=None), payload={})
    monkeypatch.setattr(services_module, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/temperature", json={"location": "Karachi"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "fortyguard_not_configured"
