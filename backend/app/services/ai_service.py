"""AI service.

Produces recommendations, outdoor-activity plans and chat answers that are
*grounded* in verified heat data. It never invents temperature values.

Two modes:
  * rule_based (default): deterministic guidance composed from the heat
    assessment. Always available; requires no external credentials.
  * llm: if AI_API_KEY, AI_BASE_URL and AI_MODEL are configured, an
    OpenAI-compatible chat-completions endpoint writes the prose using ONLY
    the supplied facts. On any failure it degrades gracefully to rule_based.

Required environment variables for the optional LLM mode are documented in
``.env.example`` and the README. No credentials are ever hard-coded.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger, redact
from app.schemas.common import RiskLevel
from app.schemas.recommendations import Activity
from app.services.heat_service import HeatAssessment, summary_for

logger = get_logger(__name__)

DISCLAIMER = (
    "AI-generated guidance grounded in the temperature data shown. General "
    "information only, not medical advice."
)

_ACTIVITY_TIP = {
    Activity.RUNNING: "Reduce pace and distance in the heat; prefer dawn or after sunset.",
    Activity.WALKING: "Choose shaded routes, slow down, and carry water.",
    Activity.OUTDOOR_WORK: "Shift heavy tasks to cooler hours and use a work/rest cycle with buddy checks.",
    Activity.COMMUTING: "Allow extra time, stay in shade/ventilation, and keep water on hand.",
    Activity.GENERAL: "Plan activity around the cooler parts of the day.",
}

# Activities that are safe to do in each risk band (informs go/no-go text).
_GO_NO_GO = {
    RiskLevel.LOW: "Generally safe.",
    RiskLevel.MODERATE: "Usually fine with basic precautions.",
    RiskLevel.HIGH: "Proceed with care; shorten and ease the effort.",
    RiskLevel.VERY_HIGH: "Not recommended right now — consider postponing.",
    RiskLevel.EXTREME: "Avoid — wait for cooler conditions.",
    RiskLevel.UNKNOWN: "Unable to advise without data; use caution.",
}


class AIService:
    """Generates grounded safety guidance, optionally via an LLM."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._transport = transport

    @property
    def is_llm_enabled(self) -> bool:
        return self._settings.ai_configured

    # ----- public API --------------------------------------------------
    async def recommend(
        self,
        *,
        activity: Activity,
        assessment: HeatAssessment | None,
        location: str | None,
        user_context: str | None,
    ) -> tuple[list[str], str, str]:
        """Return (recommendations, summary, generated_by)."""
        recommendations = self._rule_recommendations(activity, assessment)
        summary = self._rule_summary(activity, assessment, location)

        if self.is_llm_enabled:
            facts = self._facts_block(assessment, location)
            prompt = (
                f"Activity: {activity.value}\n"
                f"{facts}\n"
                f"User context: {user_context or 'none'}\n\n"
                "Write 3-5 concise, practical heat-safety recommendations for this "
                "activity as a plain bullet list, then a one-sentence summary. Use "
                "ONLY the facts above; never state a temperature that is not given."
            )
            text = await self._safe_complete(self._system_prompt(), prompt)
            if text:
                bullets = self._extract_bullets(text)
                if bullets:
                    return bullets, summary, "llm"
        return recommendations, summary, "rule_based"

    async def answer_chat(
        self,
        *,
        question: str,
        assessment: HeatAssessment | None,
        location: str | None,
    ) -> tuple[str, str]:
        """Return (answer, generated_by)."""
        rule_answer = self._rule_chat(question, assessment, location)
        if self.is_llm_enabled:
            facts = self._facts_block(assessment, location)
            prompt = (
                f"{facts}\n\nUser question: {question}\n\n"
                "Answer in 2-4 sentences. Ground the answer in the facts above; "
                "never invent a temperature. Clearly separate what the data says "
                "from general advice."
            )
            text = await self._safe_complete(self._system_prompt(), prompt)
            if text:
                return text.strip(), "llm"
        return rule_answer, "rule_based"

    def plan(
        self,
        *,
        activity: Activity,
        assessment: HeatAssessment | None,
        location: str | None,
    ) -> tuple[str, str | None, str]:
        """Return (recommended_window, avoid_window, explanation).

        Deterministic and based on current conditions plus general daily heat
        patterns — this is not a temperature forecast.
        """
        if assessment is None:
            return (
                "Early morning (before ~09:00) or evening (after ~18:00).",
                "Midday to late afternoon (roughly 11:00-16:00).",
                "No live temperature data was available, so this reflects general "
                "hot-weather timing rather than conditions for your location.",
            )

        level = assessment.risk_level
        temp_c = assessment.reading.temperature_celsius
        if level in (RiskLevel.LOW, RiskLevel.MODERATE):
            window = "Most of the day is acceptable; mornings and evenings are most comfortable."
            avoid = "The hottest part of the afternoon if the activity is strenuous."
        elif level == RiskLevel.HIGH:
            window = "Early morning (before ~09:00) or evening (after ~18:00)."
            avoid = "Late morning to late afternoon (roughly 11:00-16:00)."
        else:  # very high / extreme / unknown
            window = "Wait for a cooler time — ideally early morning or after sunset."
            avoid = "Daytime heat, especially 11:00-17:00."

        explanation = (
            f"Current conditions near {location or 'the location'} indicate "
            f"{summary_for(level).lower()} (measured {temp_c:.1f}°C). "
            "Timing guidance reflects current conditions and typical daily heat "
            "patterns, not a forecast."
        )
        return window, avoid, explanation

    # ----- rule-based generators --------------------------------------
    def _rule_recommendations(
        self, activity: Activity, assessment: HeatAssessment | None
    ) -> list[str]:
        tip = _ACTIVITY_TIP.get(activity, _ACTIVITY_TIP[Activity.GENERAL])
        if assessment is None:
            return [
                "Live temperature data is unavailable, so this is general guidance.",
                tip,
                "Hydrate, seek shade, and avoid the hottest hours (roughly 11:00-16:00).",
            ]
        return [tip, *assessment.recommended_actions]

    def _rule_summary(
        self, activity: Activity, assessment: HeatAssessment | None, location: str | None
    ) -> str:
        where = f" in {location}" if location else ""
        if assessment is None:
            return (
                f"General heat-safety guidance for {activity.value}{where}. "
                "Live temperature data was not available."
            )
        level = assessment.risk_level
        temp_c = assessment.reading.temperature_celsius
        feels = ""
        if assessment.heat_index_celsius is not None:
            feels = f", feels like {assessment.heat_index_celsius:.0f}°C"
        return (
            f"For {activity.value}{where}: {summary_for(level).lower()} "
            f"(measured {temp_c:.0f}°C{feels}). {_GO_NO_GO[level]}"
        )

    def _rule_chat(
        self, question: str, assessment: HeatAssessment | None, location: str | None
    ) -> str:
        if assessment is None:
            return (
                "I don't have live temperature data for that location, so I can't "
                "confirm current conditions. In general: hydrate, favour shaded "
                "routes, avoid the hottest hours (roughly 11:00-16:00), and stop if "
                "you feel unwell. " + DISCLAIMER
            )
        level = assessment.risk_level
        temp_c = assessment.reading.temperature_celsius
        feels = (
            f" (feels like ~{assessment.heat_index_celsius:.0f}°C)"
            if assessment.heat_index_celsius is not None
            else ""
        )
        where = f" in {location}" if location else ""
        top_actions = "; ".join(assessment.recommended_actions[:2])
        return (
            f"Data{where}: it is {temp_c:.0f}°C{feels}, a "
            f"{level.value.replace('_', ' ')} heat-risk level "
            f"({assessment.risk_level_source} classification). "
            f"{_GO_NO_GO[level]} Suggested precautions: {top_actions} {DISCLAIMER}"
        )

    # ----- LLM plumbing (OpenAI-compatible) ---------------------------
    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a careful heat-safety assistant. Use only the temperature "
            "facts provided in the user message; never fabricate temperature or "
            "weather values. Distinguish measured data from general advice. Do not "
            "give medical diagnoses. Keep answers concise and practical."
        )

    @staticmethod
    def _facts_block(assessment: HeatAssessment | None, location: str | None) -> str:
        if assessment is None:
            return (
                "FACTS: No live temperature data is available for this request."
            )
        r = assessment.reading
        lines = [
            "FACTS (verified data — do not contradict or extend beyond these):",
            f"- Location: {location or r.location or 'unspecified'}",
            f"- Temperature: {r.temperature_celsius:.1f} °C",
        ]
        if assessment.heat_index_celsius is not None:
            lines.append(f"- Feels like (heat index): {assessment.heat_index_celsius:.1f} °C")
        if r.humidity_percent is not None:
            lines.append(f"- Humidity: {r.humidity_percent:.0f}%")
        lines.append(
            f"- Heat risk level: {assessment.risk_level.value} "
            f"({assessment.risk_level_source})"
        )
        return "\n".join(lines)

    async def _safe_complete(self, system: str, user: str) -> str | None:
        """Call the LLM, returning None (and logging) on any failure."""
        try:
            return await self._complete(system, user)
        except AIServiceError as exc:
            logger.warning("AI provider failed; falling back to rule-based. %s", exc)
            return None

    async def _complete(self, system: str, user: str) -> str:
        s = self._settings
        base = (s.ai_base_url or "").rstrip("/")
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {s.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": s.ai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 400,
        }
        logger.info("Calling AI provider model=%s key=%s", s.ai_model, redact(s.ai_api_key))
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(s.ai_timeout_seconds), transport=self._transport
            ) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise AIServiceError(f"AI request failed: {exc.__class__.__name__}") from exc

        if resp.status_code >= 400:
            raise AIServiceError(f"AI provider returned status {resp.status_code}.")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("AI provider returned an unexpected response.") from exc

    @staticmethod
    def _extract_bullets(text: str) -> list[str]:
        bullets: list[str] = []
        for raw in text.splitlines():
            line = raw.strip().lstrip("-*•0123456789. ").strip()
            if line and not line.lower().startswith("summary"):
                bullets.append(line)
        return bullets[:6]
