"""Heat intelligence service.

Turns a :class:`NormalizedTemperature` reading into a risk assessment.

Risk policy:
  * If FortyGuard supplies an official risk/category value that maps cleanly
    onto our levels, that official value is used (source = "fortyguard").
  * Otherwise a documented heuristic is applied (source = "calculated"),
    based on the US NWS Heat Index categories. When relative humidity is
    available the apparent temperature (heat index) is computed using the
    NWS Rothfusz regression; otherwise the dry-bulb temperature is used.

This is general environmental guidance, NOT medical advice, and makes no
diagnostic claims.
"""

from __future__ import annotations

from math import sqrt

from pydantic import BaseModel

from app.core.logging import get_logger
from app.schemas.common import RiskLevel
from app.schemas.temperature import NormalizedTemperature

logger = get_logger(__name__)

DISCLAIMER = (
    "This is general, informational heat-safety guidance and not medical "
    "advice. Individual heat tolerance varies; if you feel unwell, stop, "
    "cool down, hydrate, and seek professional help."
)

# NWS Heat Index category boundaries, converted from °F to °C.
#   Caution        >= 80°F  (26.7°C)
#   Extreme Caution>= 90°F  (32.2°C)
#   Danger         >= 103°F (39.4°C)
#   Extreme Danger >= 125°F (51.7°C)
_BOUND_MODERATE = 26.7
_BOUND_HIGH = 32.2
_BOUND_VERY_HIGH = 39.4
_BOUND_EXTREME = 51.7

# Maps common upstream category words onto our normalised levels.
_OFFICIAL_MAP = {
    "low": RiskLevel.LOW,
    "none": RiskLevel.LOW,
    "safe": RiskLevel.LOW,
    "minimal": RiskLevel.LOW,
    "moderate": RiskLevel.MODERATE,
    "caution": RiskLevel.MODERATE,
    "elevated": RiskLevel.MODERATE,
    "high": RiskLevel.HIGH,
    "extreme caution": RiskLevel.HIGH,
    "very high": RiskLevel.VERY_HIGH,
    "danger": RiskLevel.VERY_HIGH,
    "severe": RiskLevel.VERY_HIGH,
    "extreme": RiskLevel.EXTREME,
    "extreme danger": RiskLevel.EXTREME,
    "hazardous": RiskLevel.EXTREME,
}

_ACTIONS = {
    RiskLevel.LOW: [
        "Conditions are generally comfortable; normal outdoor activity is fine.",
        "Carry water and take breaks on longer or more strenuous outings.",
    ],
    RiskLevel.MODERATE: [
        "Stay hydrated and take regular breaks in the shade.",
        "Prefer early-morning or evening hours for strenuous activity.",
        "Wear light, loose, breathable clothing and use sun protection.",
    ],
    RiskLevel.HIGH: [
        "Limit strenuous outdoor activity, especially between 11:00 and 16:00.",
        "Drink water frequently, before you feel thirsty.",
        "Take frequent breaks in shade or air conditioning.",
        "Watch for heavy sweating, dizziness, headache or cramps and stop if they appear.",
    ],
    RiskLevel.VERY_HIGH: [
        "Avoid strenuous outdoor activity; reschedule to a cooler time if possible.",
        "Stay in shade or air conditioning and hydrate continuously.",
        "Do not leave people or pets in parked vehicles.",
        "Check on vulnerable people (older adults, young children, outdoor workers).",
    ],
    RiskLevel.EXTREME: [
        "Avoid outdoor exertion; stay indoors in a cool space where possible.",
        "Hydrate continuously and use active cooling (fans, damp cloths, cool showers).",
        "Treat signs of heat illness (confusion, fainting, hot dry skin) as urgent.",
        "Check frequently on anyone at higher risk of heat harm.",
    ],
    RiskLevel.UNKNOWN: [
        "Temperature data was unavailable; follow general hot-weather precautions.",
        "Hydrate, seek shade, and avoid strenuous activity during the hottest hours.",
    ],
}

_LEVEL_SUMMARY = {
    RiskLevel.LOW: "Low heat risk.",
    RiskLevel.MODERATE: "Moderate heat risk — some caution advised.",
    RiskLevel.HIGH: "High heat risk — take active precautions.",
    RiskLevel.VERY_HIGH: "Very high heat risk — limit outdoor exposure.",
    RiskLevel.EXTREME: "Extreme heat risk — avoid outdoor exposure.",
    RiskLevel.UNKNOWN: "Heat risk could not be determined.",
}


class HeatAssessment(BaseModel):
    """Internal result combining a reading with its risk interpretation."""

    reading: NormalizedTemperature
    risk_level: RiskLevel
    risk_level_source: str  # "fortyguard" | "calculated"
    heat_index_celsius: float | None
    explanation: str
    recommended_actions: list[str]
    disclaimer: str = DISCLAIMER


class HeatService:
    """Computes heat-risk assessments from normalised readings."""

    def assess(self, reading: NormalizedTemperature) -> HeatAssessment:
        heat_index = self._heat_index_celsius(
            reading.temperature_celsius, reading.humidity_percent
        )
        effective_c = heat_index if heat_index is not None else reading.temperature_celsius

        official = self._map_official(reading.official_risk_level)
        if official is not None:
            level = official
            source = "fortyguard"
        else:
            level = self._classify(effective_c)
            source = "calculated"

        explanation = self._explain(reading, effective_c, heat_index, level, source)
        return HeatAssessment(
            reading=reading,
            risk_level=level,
            risk_level_source=source,
            heat_index_celsius=None if heat_index is None else round(heat_index, 1),
            explanation=explanation,
            recommended_actions=_ACTIONS[level],
        )

    # ----- risk logic --------------------------------------------------
    @staticmethod
    def _map_official(value: str | None) -> RiskLevel | None:
        if not value:
            return None
        return _OFFICIAL_MAP.get(value.strip().lower())

    @staticmethod
    def _classify(effective_c: float) -> RiskLevel:
        if effective_c < _BOUND_MODERATE:
            return RiskLevel.LOW
        if effective_c < _BOUND_HIGH:
            return RiskLevel.MODERATE
        if effective_c < _BOUND_VERY_HIGH:
            return RiskLevel.HIGH
        if effective_c < _BOUND_EXTREME:
            return RiskLevel.VERY_HIGH
        return RiskLevel.EXTREME

    @staticmethod
    def _heat_index_celsius(temp_c: float, humidity: float | None) -> float | None:
        """NWS Rothfusz heat index in °C, or None when not applicable.

        The regression is only meaningful for warm, humid conditions
        (T >= ~80°F / 26.7°C); below that the dry temperature is used.
        """
        if humidity is None:
            return None
        t_f = temp_c * 9.0 / 5.0 + 32.0
        if t_f < 80.0:
            return None
        rh = max(0.0, min(100.0, humidity))
        hi = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * rh
            - 0.22475541 * t_f * rh
            - 0.00683783 * t_f * t_f
            - 0.05481717 * rh * rh
            + 0.00122874 * t_f * t_f * rh
            + 0.00085282 * t_f * rh * rh
            - 0.00000199 * t_f * t_f * rh * rh
        )
        if rh < 13 and 80 <= t_f <= 112:
            hi -= ((13 - rh) / 4) * sqrt((17 - abs(t_f - 95)) / 17)
        elif rh > 85 and 80 <= t_f <= 87:
            hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
        return (hi - 32.0) * 5.0 / 9.0

    @staticmethod
    def _explain(
        reading: NormalizedTemperature,
        effective_c: float,
        heat_index: float | None,
        level: RiskLevel,
        source: str,
    ) -> str:
        parts = [_LEVEL_SUMMARY[level]]
        parts.append(f"Measured temperature is {reading.temperature_celsius:.1f}°C.")
        if heat_index is not None:
            parts.append(
                f"With {reading.humidity_percent:.0f}% humidity it feels like "
                f"about {heat_index:.1f}°C (heat index)."
            )
        if source == "fortyguard":
            parts.append(
                f"Risk level '{reading.official_risk_level}' is reported directly "
                "by the FortyGuard API."
            )
        else:
            parts.append(
                "Risk level is calculated from temperature using US NWS Heat "
                "Index categories."
            )
        return " ".join(parts)


def summary_for(level: RiskLevel) -> str:
    """Public helper for other services needing a one-line level summary."""
    return _LEVEL_SUMMARY.get(level, _LEVEL_SUMMARY[RiskLevel.UNKNOWN])
