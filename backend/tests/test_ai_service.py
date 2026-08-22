"""Tests for the AI service: grounding, rule-based fallback, and LLM path.

No real AI provider is called — the LLM HTTP layer is mocked.
"""

from __future__ import annotations

import asyncio

import httpx

from app.schemas.recommendations import Activity
from app.schemas.temperature import NormalizedTemperature
from app.services.ai_service import AIService
from app.services.heat_service import HeatService
from tests.conftest import make_settings, transport_json, transport_raising


def _assessment(temp_c: float = 40.0):
    reading = NormalizedTemperature(
        location="Karachi",
        temperature=temp_c,
        unit="°C",
        temperature_celsius=temp_c,
    )
    return HeatService().assess(reading)


def test_rule_based_recommendations_are_grounded():
    svc = AIService(make_settings())  # AI not configured -> rule_based
    assert svc.is_llm_enabled is False

    recs, summary, generated_by = asyncio.run(
        svc.recommend(
            activity=Activity.RUNNING,
            assessment=_assessment(40.0),
            location="Karachi",
            user_context=None,
        )
    )
    assert generated_by == "rule_based"
    assert recs
    assert "°C" in summary  # grounded in the measured temperature


def test_rule_based_without_data_notes_unavailable():
    svc = AIService(make_settings())
    recs, summary, generated_by = asyncio.run(
        svc.recommend(
            activity=Activity.WALKING,
            assessment=None,
            location=None,
            user_context=None,
        )
    )
    assert generated_by == "rule_based"
    assert any("unavailable" in r.lower() for r in recs)


def test_chat_falls_back_when_llm_errors():
    settings = make_settings(
        ai_api_key="k", ai_base_url="https://ai.test/v1", ai_model="m"
    )
    svc = AIService(
        settings,
        transport=transport_raising(lambda req: httpx.ConnectError("down", request=req)),
    )
    assert svc.is_llm_enabled is True

    answer, generated_by = asyncio.run(
        svc.answer_chat(question="Can I run now?", assessment=_assessment(41.0), location="Karachi")
    )
    # Graceful degradation: no exception, grounded rule-based answer returned.
    assert generated_by == "rule_based"
    assert "41" in answer or "°C" in answer


def test_chat_uses_llm_when_configured_and_healthy():
    settings = make_settings(
        ai_api_key="k", ai_base_url="https://ai.test/v1", ai_model="m"
    )
    payload = {"choices": [{"message": {"content": "It's hot; keep it short and hydrate."}}]}
    svc = AIService(settings, transport=transport_json(payload))

    answer, generated_by = asyncio.run(
        svc.answer_chat(question="Can I run now?", assessment=_assessment(41.0), location="Karachi")
    )
    assert generated_by == "llm"
    assert "hydrate" in answer.lower()
