"""
BuilderPulse error codes — programmatic error identification for MCP clients and Agent output.

All codes are strings (not ints) so they are JSON-safe and human-readable.
Core codes are defined as an enum; plugin codes are registered at runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional


# ── Core error codes ────────────────────────────────────────────────────


class ErrorCode(str, Enum):
    """Built-in BuilderPulse error codes."""

    # Download phase
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    DOWNLOAD_TIMEOUT = "DOWNLOAD_TIMEOUT"
    DOWNLOAD_FORBIDDEN = "DOWNLOAD_FORBIDDEN"

    # Transcribe phase
    TRANSCRIBE_FAILED = "TRANSCRIBE_FAILED"
    TRANSCRIBE_NO_AUDIO = "TRANSCRIBE_NO_AUDIO"
    TRANSCRIBE_ENGINE_UNAVAILABLE = "TRANSCRIBE_ENGINE_UNAVAILABLE"

    # Summarize phase
    SUMMARIZE_FAILED = "SUMMARIZE_FAILED"
    SUMMARIZE_QUOTA_EXCEEDED = "SUMMARIZE_QUOTA_EXCEEDED"

    # Translate phase
    TRANSLATE_FAILED = "TRANSLATE_FAILED"

    # Deliver phase
    DELIVER_FAILED = "DELIVER_FAILED"
    DELIVER_RATE_LIMITED = "DELIVER_RATE_LIMITED"

    # Batch orchestration
    BATCH_ITEM_FAILED = "BATCH_ITEM_FAILED"
    BATCH_DISK_FULL = "BATCH_DISK_FULL"

    # Config
    CONFIG_NOT_FOUND = "CONFIG_NOT_FOUND"
    CONFIG_INVALID = "CONFIG_INVALID"


# ── Plugin code registry ────────────────────────────────────────────────

_PLUGIN_CODES: Dict[str, dict] = {}


def register_plugin_code(plugin: str, code: str, desc: str) -> str:
    """Register a plugin-specific error code and return the full code string.

    The returned string has the form ``PLUGIN_{plugin}_{code}`` (uppercased).
    Registration is idempotent — re-registering the same plugin+code is safe.
    """
    full_code = f"PLUGIN_{plugin.upper()}_{code.upper()}"
    _PLUGIN_CODES[full_code] = {
        "plugin": plugin.lower(),
        "code": code.upper(),
        "description": desc,
    }
    return full_code


def get_error_info(code: str) -> dict:
    """Return metadata for an error code.

    For core codes returns ``{"type": "core", "code": "<code>", ...}``.
    For plugin codes returns ``{"type": "plugin", "plugin": "<name>", ...}``.
    Unknown codes return ``{"type": "unknown", "code": "<code>"}``.
    """
    # Check plugin codes first
    if code in _PLUGIN_CODES:
        return {"type": "plugin", **_PLUGIN_CODES[code]}

    # Check core codes
    try:
        ErrorCode(code)
        return {"type": "core", "code": code}
    except ValueError:
        pass

    return {"type": "unknown", "code": code}
