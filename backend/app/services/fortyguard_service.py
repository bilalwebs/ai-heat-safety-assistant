"""FortyGuard Temperature API adapter.

This module is the single integration seam with the FortyGuard Temperature
API (https://docs-api.fortyguard.com). Everything vendor-specific lives here;
the rest of the application depends only on the internal
:class:`NormalizedTemperature` schema.

────────────────────────────────────────────────────────────────────────
 FORTYGUARD CONTRACT — READ THIS
────────────────────────────────────────────────────────────────────────
The exact request/response contract (endpoint path, auth header, parameter
names and response field names) was NOT available in this workspace and the
public docs are JavaScript-rendered, so nothing here is *guessed and hidden*.
Instead the contract is expressed as configuration:

  * FORTYGUARD_BASE_URL             e.g. https://api.fortyguard.com
  * FORTYGUARD_TEMPERATURE_PATH     the real temperature endpoint path
  * FORTYGUARD_API_KEY              your key
  * FORTYGUARD_AUTH_HEADER / _SCHEME   how the key is sent
  * FORTYGUARD_HTTP_METHOD / _REQUEST_STYLE  GET+query vs POST+json
  * FORTYGUARD_*_PARAM              outgoing parameter names

Until FORTYGUARD_BASE_URL, FORTYGUARD_TEMPERATURE_PATH and FORTYGUARD_API_KEY
are all set, the service returns HTTP 503 rather than calling a placeholder
endpoint or fabricating data.

Response normalisation (:meth:`_normalize`) searches common field names and
should be adjusted to match the confirmed response shape. If no temperature
value is found it raises rather than inventing one.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import (
    FortyGuardNotConfiguredError,
    FortyGuardResponseError,
    FortyGuardTimeoutError,
    FortyGuardUnavailableError,
    FortyGuardUpstreamError,
    LocationNotFoundError,
)
from app.core.logging import get_logger, redact, redact_headers
from app.schemas.temperature import NormalizedTemperature, TemperatureQuery

logger = get_logger(__name__)

# Candidate field names searched during normalisation. Extend/reorder these
# once the real FortyGuard response shape is confirmed.
_TEMP_KEYS = (
    "temperature",
    "temp",
    "air_temperature",
    "temperature_c",
    "temperatureC",
    "celsius",
    "value",
)
_UNIT_KEYS = ("unit", "units", "temperature_unit")
_HUMIDITY_KEYS = ("humidity", "humidity_percent", "relative_humidity", "rh")
_RISK_KEYS = ("risk_level", "risk", "heat_risk", "category", "severity")
_RESOLUTION_KEYS = ("resolution", "precision", "spatial_resolution")
_TIME_KEYS = ("measured_at", "timestamp", "time", "observed_at", "datetime")


class FortyGuardService:
    """Async client for the FortyGuard Temperature API."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # ----- lifecycle ---------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return self._settings.fortyguard_configured

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.fortyguard_base_url or "",
                timeout=httpx.Timeout(self._settings.fortyguard_timeout_seconds),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- public API --------------------------------------------------
    async def get_temperature(self, query: TemperatureQuery) -> NormalizedTemperature:
        """Fetch and normalise a temperature reading for ``query``.

        Raises a :class:`~app.core.exceptions.HeatAssistantError` subclass on
        any failure; never returns fabricated data.
        """
        if not self.is_configured:
            raise FortyGuardNotConfiguredError()

        client = self._get_client()
        method = self._settings.fortyguard_http_method.upper()
        path = self._settings.fortyguard_temperature_path or ""
        request_kwargs = self._build_request(query)

        logger.info(
            "Calling FortyGuard %s %s (auth via %s: %s)",
            method,
            path,
            self._settings.fortyguard_auth_header,
            redact(self._settings.fortyguard_api_key),
        )

        try:
            response = await client.request(method, path, **request_kwargs)
        except httpx.TimeoutException as exc:
            logger.warning("FortyGuard request timed out: %s", exc)
            raise FortyGuardTimeoutError() from exc
        except httpx.TransportError as exc:  # connection/DNS/TLS errors
            logger.warning("FortyGuard connection error: %s", exc)
            raise FortyGuardUnavailableError() from exc

        self._raise_for_status(response)

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("FortyGuard returned non-JSON body (%s bytes)", len(response.content))
            raise FortyGuardResponseError(
                "The FortyGuard API returned a non-JSON response."
            ) from exc

        return self._normalize(data, query)

    # ----- internals ---------------------------------------------------
    def _auth_headers(self) -> dict[str, str]:
        scheme = self._settings.fortyguard_auth_scheme.strip()
        key = self._settings.fortyguard_api_key or ""
        value = f"{scheme} {key}".strip() if scheme else key
        return {self._settings.fortyguard_auth_header: value, "Accept": "application/json"}

    def _build_request(self, query: TemperatureQuery) -> dict[str, Any]:
        s = self._settings
        payload: dict[str, Any] = {}
        if query.latitude is not None and query.longitude is not None:
            payload[s.fortyguard_lat_param] = query.latitude
            payload[s.fortyguard_lon_param] = query.longitude
        if query.location:
            payload[s.fortyguard_location_param] = query.location

        headers = self._auth_headers()
        logger.debug("FortyGuard headers: %s", redact_headers(headers))

        if s.fortyguard_request_style.lower() == "json":
            return {"headers": headers, "json": payload}
        return {"headers": headers, "params": payload}

    def _raise_for_status(self, response: httpx.Response) -> None:
        code = response.status_code
        if code == 404:
            raise LocationNotFoundError()
        if code == 429:
            logger.warning("FortyGuard rate limit hit (429).")
            raise FortyGuardUnavailableError(
                "The FortyGuard API rate limit was exceeded. Please retry later."
            )
        if 400 <= code < 500:
            logger.warning("FortyGuard client error %s: %s", code, self._safe_snippet(response))
            raise FortyGuardUpstreamError(
                f"The FortyGuard API rejected the request (status {code})."
            )
        if code >= 500:
            logger.warning("FortyGuard server error %s", code)
            raise FortyGuardUnavailableError()

    def _normalize(self, data: Any, query: TemperatureQuery) -> NormalizedTemperature:
        """Map the raw vendor payload into our internal schema.

        Adjust the candidate key lists at module top once the real response
        shape is confirmed. Missing temperature -> hard error (never faked).
        """
        record = self._select_record(data)

        raw_temp = self._deep_find(record, _TEMP_KEYS)
        temperature = self._to_float(raw_temp)
        if temperature is None:
            logger.warning("No temperature field found in FortyGuard response.")
            raise FortyGuardResponseError(
                "Could not locate a temperature value in the FortyGuard response."
            )

        unit_raw = self._deep_find(record, _UNIT_KEYS)
        unit_label, temperature_celsius = self._normalize_unit(temperature, unit_raw)

        return NormalizedTemperature(
            location=query.location,
            latitude=query.latitude,
            longitude=query.longitude,
            temperature=temperature,
            unit=unit_label,
            temperature_celsius=round(temperature_celsius, 2),
            humidity_percent=self._to_float(self._deep_find(record, _HUMIDITY_KEYS)),
            official_risk_level=self._stringify(self._deep_find(record, _RISK_KEYS)),
            resolution=self._stringify(self._deep_find(record, _RESOLUTION_KEYS)),
            measured_at=self._stringify(self._deep_find(record, _TIME_KEYS)),
            source="fortyguard",
        )

    # ----- normalisation helpers --------------------------------------
    @staticmethod
    def _select_record(data: Any) -> Any:
        """Unwrap common envelope shapes to reach the reading object."""
        if isinstance(data, dict):
            for key in ("data", "result", "results", "response"):
                if key in data:
                    inner = data[key]
                    return inner[0] if isinstance(inner, list) and inner else inner
            return data
        if isinstance(data, list) and data:
            return data[0]
        return data

    @classmethod
    def _deep_find(cls, data: Any, keys: tuple[str, ...]) -> Any:
        """Case-insensitive, recursive search for the first matching key."""
        wanted = {k.lower() for k in keys}
        if isinstance(data, dict):
            for k, v in data.items():
                if k.lower() in wanted and not isinstance(v, (dict, list)):
                    return v
            for v in data.values():
                found = cls._deep_find(v, keys)
                if found is not None:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = cls._deep_find(item, keys)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _normalize_unit(temperature: float, unit_raw: Any) -> tuple[str, float]:
        """Return a display unit label and the Celsius-converted value."""
        unit = str(unit_raw).strip().lower() if unit_raw is not None else "c"
        if unit in ("f", "°f", "fahrenheit"):
            return "°F", (temperature - 32.0) * 5.0 / 9.0
        if unit in ("k", "kelvin"):
            return "K", temperature - 273.15
        return "°C", temperature

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stringify(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _safe_snippet(response: httpx.Response, limit: int = 200) -> str:
        """A short, secret-free snippet of an error body for logging."""
        try:
            text = response.text
        except Exception:  # pragma: no cover - defensive
            return "<unreadable body>"
        return text[:limit].replace("\n", " ")
