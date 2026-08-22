"""Convenience entry point for running the development server.

Usage:
    python run.py

Environment variables HOST and PORT override the defaults.
"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
