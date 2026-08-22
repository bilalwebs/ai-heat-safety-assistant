"""Tests for the health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

SECRET_MARKERS = ("key", "secret", "token", "password")


def test_health_returns_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_does_not_leak_secrets():
    with TestClient(app) as client:
        resp = client.get("/health")
    body = resp.json()
    # Readiness flags are booleans; no secret values are present anywhere.
    assert isinstance(body["fortyguard_configured"], bool)
    assert isinstance(body["ai_llm_enabled"], bool)
    for key, value in body.items():
        lowered = key.lower()
        assert not any(marker in lowered for marker in SECRET_MARKERS), key
        assert "test-key" not in str(value)
