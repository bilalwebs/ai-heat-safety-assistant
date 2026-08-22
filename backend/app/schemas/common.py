"""Shared schema types used across multiple endpoints."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Normalised heat-risk levels used throughout the application.

    The ordering (low -> extreme) reflects increasing severity.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    EXTREME = "extreme"
    UNKNOWN = "unknown"


class ErrorBody(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")
    status_code: int = Field(..., description="HTTP status code.")


class ErrorResponse(BaseModel):
    """Consistent error envelope returned for all handled failures."""

    error: ErrorBody
