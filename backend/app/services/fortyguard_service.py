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

import asyncio
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import (
    FortyGuardActivityNotFoundError,
    FortyGuardNotConfiguredError,
    FortyGuardResponseError,
    FortyGuardTaskFailedError,
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

# ---------------------------------------------------------------------------
# Async heatmap workflow (verified against the official quickstart client).
#   submit:  POST /v1/heatmap                 -> data.activity_id
#   poll:    GET  /v1/status/{activity_id}    -> data.status (+ data.result)
# Auth is the custom `api-key` header (NOT Authorization: Bearer).
# ---------------------------------------------------------------------------
_HEATMAP_PATH = "/v1/heatmap"
_STATUS_PATH = "/v1/status/{activity_id}"

# status values are lower-cased before comparison
_TERMINAL_SUCCESS = frozenset({"succeeded", "completed", "success", "done"})
_TERMINAL_FAILURE = frozenset({"failed", "error", "failure"})


class _ActivityNotReady(Exception):
    """Internal signal: the status endpoint 404'd (result not visible yet)."""


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

    # ----- heatmap (async submit -> poll workflow) ---------------------
    def _heatmap_headers(self) -> dict[str, str]:
        """Verified FortyGuard auth for the async endpoints.

        The header is the custom ``api-key`` (NOT ``Authorization: Bearer``).
        Built explicitly here so the heatmap flow is robust to any stale
        ``FORTYGUARD_AUTH_*`` values left over from the legacy config.
        """
        return {
            "api-key": self._settings.fortyguard_api_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def submit_heatmap(self, payload: dict[str, Any]) -> str:
        """Submit a heatmap job and return its ``activity_id``.

        ``payload`` must already be the verified FortyGuard body (see
        :meth:`app.schemas.heatmap.HeatmapRequest.to_payload`). Never logs the
        payload or the key — only that a submit started and the resulting id.
        """
        if not self._settings.fortyguard_ready:
            raise FortyGuardNotConfiguredError()

        client = self._get_client()
        logger.info(
            "FortyGuard heatmap submit: POST %s (auth via api-key: %s)",
            _HEATMAP_PATH,
            redact(self._settings.fortyguard_api_key),
        )
        try:
            response = await client.post(
                _HEATMAP_PATH, headers=self._heatmap_headers(), json=payload
            )
        except httpx.TimeoutException as exc:
            logger.warning("FortyGuard submit timed out: %s", exc)
            raise FortyGuardTimeoutError() from exc
        except httpx.TransportError as exc:
            logger.warning("FortyGuard submit connection error: %s", exc)
            raise FortyGuardUnavailableError() from exc

        self._raise_for_status(response)
        data = self._parse_json(response)
        if isinstance(data, dict) and data.get("error"):
            raise FortyGuardUpstreamError(self._error_message(data))

        activity_id = self._extract_activity_id(data)
        logger.info("FortyGuard heatmap submitted: activity_id=%s", activity_id)
        return activity_id

    async def get_activity(self, activity_id: str) -> dict[str, Any]:
        """Fetch the current status/result object for ``activity_id``.

        Returns the upstream ``data`` object (contains ``status`` and, once
        finished, ``result``). Raises :class:`_ActivityNotReady` on a 404 so
        callers can distinguish "not visible yet" from a real error.
        """
        if not self._settings.fortyguard_ready:
            raise FortyGuardNotConfiguredError()

        client = self._get_client()
        path = _STATUS_PATH.format(activity_id=activity_id)
        try:
            response = await client.get(path, headers=self._heatmap_headers())
        except httpx.TimeoutException as exc:
            logger.warning("FortyGuard status timed out: %s", exc)
            raise FortyGuardTimeoutError() from exc
        except httpx.TransportError as exc:
            logger.warning("FortyGuard status connection error: %s", exc)
            raise FortyGuardUnavailableError() from exc

        if response.status_code == 404:
            # Eventual consistency: the id may not be queryable yet.
            raise _ActivityNotReady(activity_id)

        self._raise_for_status(response)
        data = self._parse_json(response)
        inner = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(inner, dict):
            raise FortyGuardResponseError(
                "The FortyGuard status response had an unexpected shape."
            )
        return inner

    async def wait_for_activity(
        self, activity_id: str, max_wait: float | None = None
    ) -> dict[str, Any] | None:
        """Poll until the job finishes, fails, or the wait budget runs out.

        Returns the completed ``data`` object (including ``result``) on success,
        ``None`` if still processing when the request-scoped budget elapses (the
        caller then returns 202 + poll URL), and raises
        :class:`FortyGuardTaskFailedError` if the upstream reports failure.
        """
        interval = max(0.0, self._settings.fortyguard_poll_interval_seconds)
        budget = (
            self._settings.fortyguard_max_wait_seconds if max_wait is None else max_wait
        )
        deadline = time.monotonic() + budget

        while True:
            try:
                data = await self.get_activity(activity_id)
                state = self.classify_status(data)
                if state == "completed":
                    logger.info("FortyGuard activity completed: activity_id=%s", activity_id)
                    return data
                if state == "failed":
                    logger.info(
                        "FortyGuard activity failed: activity_id=%s status=%s",
                        activity_id,
                        data.get("status"),
                    )
                    raise FortyGuardTaskFailedError(
                        f"The FortyGuard task did not complete "
                        f"(status={str(data.get('status') or '').lower()})."
                    )
            except _ActivityNotReady:
                pass  # not visible yet — keep polling within budget

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.info(
                    "FortyGuard activity still processing after %.0fs: activity_id=%s",
                    budget,
                    activity_id,
                )
                return None
            await asyncio.sleep(min(interval, remaining) if interval > 0 else 0)

    async def fetch_activity(self, activity_id: str) -> dict[str, Any]:
        """Public single status fetch for the standalone GET endpoint.

        Unlike :meth:`get_activity`, a 404 here means the id is unknown or
        expired (the submit+wait flow only returns an id once it is queryable),
        so it maps to :class:`FortyGuardActivityNotFoundError` (HTTP 404).
        """
        try:
            return await self.get_activity(activity_id)
        except _ActivityNotReady as exc:
            raise FortyGuardActivityNotFoundError() from exc

    # ----- internals ---------------------------------------------------
    @staticmethod
    def _parse_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise FortyGuardResponseError(
                "The FortyGuard API returned a non-JSON response."
            ) from exc

    @staticmethod
    def classify_status(data: dict[str, Any]) -> str:
        """Map an upstream status object to completed | failed | processing."""
        status = str(data.get("status") or "").strip().lower()
        if status in _TERMINAL_SUCCESS:
            return "completed"
        if status in _TERMINAL_FAILURE:
            return "failed"
        return "processing"

    @staticmethod
    def extract_result(data: Any) -> dict[str, Any] | None:
        """Pull the ``result`` payload from a completed status object.

        Falls back to the whole status object if no nested ``result`` is
        present, so a caller always gets the richest dict available.
        """
        if not isinstance(data, dict):
            return None
        result = data.get("result")
        return result if isinstance(result, dict) else data

    @staticmethod
    def _extract_activity_id(data: Any) -> str:
        """Pull ``activity_id`` from the verified ``{"data": {...}}`` envelope."""
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict) and inner.get("activity_id"):
                return str(inner["activity_id"])
            if data.get("activity_id"):
                return str(data["activity_id"])
        raise FortyGuardResponseError(
            "The FortyGuard submit response did not include an activity_id."
        )

    @staticmethod
    def _error_message(data: dict[str, Any]) -> str:
        msg = data.get("message") or data.get("error") or "FortyGuard reported an error."
        return str(msg)[:200]

    @staticmethod
    def extract_stats_and_count(result: Any) -> tuple[dict[str, Any] | None, int | None]:
        """Best-effort summary of a completed result: (stats_data, feature count).

        Only reads keys verified present in a live response (``stats_data``;
        ``map_data.features``); returns ``None`` when absent rather than
        assuming a shape.
        """
        stats: dict[str, Any] | None = None
        count: int | None = None
        if isinstance(result, dict):
            sd = result.get("stats_data")
            if isinstance(sd, dict):
                stats = sd
            md = result.get("map_data")
            if isinstance(md, dict):
                feats = md.get("features")
                if isinstance(feats, list):
                    count = len(feats)
        return stats, count

    @staticmethod
    def _first_feature_props(result: Any) -> dict[str, Any] | None:
        if isinstance(result, dict):
            md = result.get("map_data")
            if isinstance(md, dict):
                feats = md.get("features")
                if isinstance(feats, list) and feats and isinstance(feats[0], dict):
                    props = feats[0].get("properties")
                    if isinstance(props, dict):
                        return props
        return None

    @classmethod
    def extract_value_key(cls, result: Any) -> str | None:
        """Infer the primary tile value property from the real tiles.

        Live-verified for tcm (``average_temperature``; tiles also carry
        min/max_temperature). Threshold analyses use ``value`` per the docs.
        Falls back to ``temperature`` if present, else ``None``.
        """
        props = cls._first_feature_props(result)
        if props is None:
            return None
        for key in ("average_temperature", "value", "temperature"):
            if key in props:
                return key
        return None

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
        if code in (401, 403):
            # The key is present but the upstream rejected it. Never echo the
            # key or the response body (may repeat request details).
            logger.warning("FortyGuard rejected credentials (status %s).", code)
            raise FortyGuardUpstreamError(
                "FortyGuard rejected the API credentials (check FORTYGUARD_API_KEY)."
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
