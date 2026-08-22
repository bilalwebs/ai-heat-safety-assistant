"""Centralised logging configuration.

The formatter never receives secrets: services are responsible for redacting
API keys before logging, and helper :func:`redact` is provided for that.
"""

from __future__ import annotations

import logging
from typing import Iterable

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, using a concise, readable format."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)


def redact(value: str | None, *, keep: int = 4) -> str:
    """Redact a secret for safe logging, revealing at most ``keep`` chars.

    ``None`` or short values are fully masked so a key can never leak.
    """
    if not value:
        return "<unset>"
    if len(value) <= keep:
        return "***"
    return f"{value[:keep]}***"


def redact_headers(headers: Iterable[tuple[str, str]] | dict[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with sensitive values masked."""
    sensitive = {"authorization", "x-api-key", "api-key", "apikey", "x-auth-token"}
    items = headers.items() if isinstance(headers, dict) else headers
    return {
        key: ("***REDACTED***" if key.lower() in sensitive else val)
        for key, val in items
    }
