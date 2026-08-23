"""Application exception hierarchy.

Every domain error carries an HTTP ``status_code`` and a stable ``code`` slug
so the API can return consistent, safe error payloads without leaking stack
traces or secrets. These are translated into JSON responses by the handlers
registered in :mod:`app.main`.
"""

from __future__ import annotations


class HeatAssistantError(Exception):
    """Base class for all expected, translatable application errors."""

    status_code: int = 500
    code: str = "internal_error"
    detail: str = "An unexpected internal error occurred."

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)


# --- FortyGuard integration errors ------------------------------------


class FortyGuardNotConfiguredError(HeatAssistantError):
    status_code = 503
    code = "fortyguard_not_configured"
    detail = (
        "The FortyGuard API is not configured on the server. Set "
        "FORTYGUARD_API_KEY and FORTYGUARD_BASE_URL (the legacy /temperature "
        "endpoint also needs FORTYGUARD_TEMPERATURE_PATH)."
    )


class FortyGuardTimeoutError(HeatAssistantError):
    status_code = 504
    code = "fortyguard_timeout"
    detail = "The FortyGuard API request timed out."


class FortyGuardUnavailableError(HeatAssistantError):
    status_code = 503
    code = "fortyguard_unavailable"
    detail = "The FortyGuard API is currently unavailable."


class FortyGuardUpstreamError(HeatAssistantError):
    status_code = 502
    code = "fortyguard_upstream_error"
    detail = "The FortyGuard API returned an error."


class FortyGuardResponseError(HeatAssistantError):
    status_code = 502
    code = "fortyguard_bad_response"
    detail = "The FortyGuard API returned an unexpected response."


class FortyGuardTaskFailedError(HeatAssistantError):
    status_code = 502
    code = "fortyguard_task_failed"
    detail = "The FortyGuard processing task failed."


class FortyGuardActivityNotFoundError(HeatAssistantError):
    status_code = 404
    code = "activity_not_found"
    detail = "No FortyGuard activity was found for the given id."


class LocationNotFoundError(HeatAssistantError):
    status_code = 404
    code = "location_not_found"
    detail = "No temperature data was found for the requested location."


# --- AI service errors -------------------------------------------------


class AIServiceError(HeatAssistantError):
    status_code = 502
    code = "ai_service_error"
    detail = "The AI service failed to generate a response."
