"""Tests for the heat intelligence service and heat-risk endpoint."""

from __future__ import annotations

import app.services as services_module
from app.schemas.common import RiskLevel
from app.schemas.temperature import NormalizedTemperature
from app.services.heat_service import HeatService
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_service


def _reading(temp_c: float, **kw) -> NormalizedTemperature:
    return NormalizedTemperature(
        location=kw.get("location", "Test"),
        temperature=temp_c,
        unit="°C",
        temperature_celsius=temp_c,
        humidity_percent=kw.get("humidity"),
        official_risk_level=kw.get("official"),
    )


def test_classification_thresholds():
    svc = HeatService()
    assert svc.assess(_reading(20)).risk_level == RiskLevel.LOW
    assert svc.assess(_reading(30)).risk_level == RiskLevel.MODERATE
    assert svc.assess(_reading(35)).risk_level == RiskLevel.HIGH
    assert svc.assess(_reading(45)).risk_level == RiskLevel.VERY_HIGH
    assert svc.assess(_reading(55)).risk_level == RiskLevel.EXTREME


def test_calculated_source_and_actions():
    result = HeatService().assess(_reading(35))
    assert result.risk_level_source == "calculated"
    assert result.recommended_actions
    assert "NWS" in result.explanation
    assert result.disclaimer


def test_official_risk_level_is_preferred():
    # Upstream says "danger" even though the raw temp would be LOW.
    result = HeatService().assess(_reading(18, official="danger"))
    assert result.risk_level == RiskLevel.VERY_HIGH
    assert result.risk_level_source == "fortyguard"


def test_heat_index_applied_with_humidity():
    result = HeatService().assess(_reading(33, humidity=70))
    assert result.heat_index_celsius is not None
    # High humidity should make it feel hotter than the dry temperature.
    assert result.heat_index_celsius > 33
    assert result.risk_level in {RiskLevel.HIGH, RiskLevel.VERY_HIGH}


def test_heat_risk_endpoint(monkeypatch):
    svc = make_service({"temperature": 45, "unit": "C"})
    monkeypatch.setattr(services_module, "get_fortyguard_service", lambda: svc)
    with TestClient(app) as client:
        resp = client.post("/api/v1/heat-risk", json={"location": "Jacobabad"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "very_high"
    assert body["risk_level_source"] == "calculated"
    assert body["recommended_actions"]
    assert body["explanation"]
    assert body["disclaimer"]
