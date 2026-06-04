"""Structured agent output model with auto-sanitization and MCP helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

# Sensitive field names — exact token match after splitting on underscores.
# E.g. ``api_key`` splits to ``["api", "key"]`` — "key" matches.
_SENSITIVE_TOKENS = frozenset({"key", "secret", "token", "password"})


def _is_sensitive(field_name: str) -> bool:
    """Return True if *field_name* contains a sensitive token.

    Splits on ``_`` and checks each segment for exact membership in
    ``_SENSITIVE_TOKENS`` to avoid false positives like ``"monkey"``.
    """
    tokens = field_name.lower().replace("-", "_").split("_")
    return bool(_SENSITIVE_TOKENS & set(tokens))


class AgentOutput(BaseModel):
    """Canonical output envelope for BuilderPulse agents.

    * ``config`` values whose keys match sensitive patterns are auto-redacted.
    * ``to_json()`` / ``to_mcp_content()`` provide ready-to-emit serialisation.
    """

    schema_version: str = "builderpulse.agent-output/v2"
    generated_at: Optional[datetime] = None
    config: Dict[str, Any]
    results: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    stats: Dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _set_generated_at(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("generated_at") is None:
            data["generated_at"] = datetime.now(timezone.utc)
        return data

    @field_validator("config", mode="before")
    @classmethod
    def _sanitize_config(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Redact values of keys that match sensitive keywords."""
        sanitized: Dict[str, Any] = {}
        for key, val in v.items():
            if _is_sensitive(key):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = val
        return sanitized

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a JSON string."""
        data = self.model_dump()
        return json.dumps(data, indent=indent, default=_json_fallback)

    def to_mcp_content(self) -> Dict[str, Any]:
        """Return an MCP-compatible ``{type, text, mimeType}`` dict."""
        return {
            "type": "text",
            "text": self.to_json(),
            "mimeType": "application/json",
        }


def _json_fallback(obj: Any) -> Any:
    """Default serialiser for types ``json.dumps`` can't handle natively."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, BaseException):
        return f"{type(obj).__name__}: {obj}"
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
