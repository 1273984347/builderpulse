"""
BuilderPulse unified configuration — env-var overrides, JSON file loading, secret masking.

All settings can be overridden via BUILDERPULSE_* environment variables.
Sensitive fields are masked in to_dict() output by default.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────

_DEFAULT_WORKSPACE = Path.home() / ".builderpulse" / "output"

SENSITIVE_KEYS = frozenset({
    "botToken",
    "apiKey",
    "apiSecret",
    "sessdata",
    "password",
    "secret",
})

# Mapping from field name → env var name
_ENV_PREFIX = "BUILDERPULSE_"


# ── Config class ───────────────────────────────────────────────────────


@dataclass
class Config:
    """Unified BuilderPulse configuration.

    Precedence (highest wins):
        1. Env vars (BUILDERPULSE_LANGUAGE, BUILDERPULSE_ENGINE, …)
        2. JSON file loaded via Config.from_file()
        3. Field defaults defined here
    """

    language: str = "en"
    engine: str = "auto"
    model: str = "base"
    device: str = "auto"
    workspace: str = str(_DEFAULT_WORKSPACE)

    # Sensitive fields — names must match SENSITIVE_KEYS entries (case-insensitive)
    telegram_bot_token: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    sessdata: Optional[str] = None

    # ── Constructors ───────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str | Path) -> Config:
        """Load configuration from a JSON file.

        Missing keys fall back to field defaults.  Env vars still override.
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Build kwargs from known field names
        known = {fld.name for fld in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}

        cfg = cls(**kwargs)
        cfg._apply_env_overrides()
        return cfg

    @classmethod
    def from_defaults(cls) -> Config:
        """Create a Config with defaults, then apply env-var overrides."""
        cfg = cls()
        cfg._apply_env_overrides()
        return cfg

    # ── Serialisation ──────────────────────────────────────────────────

    def to_dict(self, mask_secrets: bool = True) -> dict:
        """Return config as a plain dict.

        When *mask_secrets* is True (default), values whose field name
        matches SENSITIVE_KEYS are replaced with "****".
        """
        result = {}
        for fld in fields(self):
            value = getattr(self, fld.name)
            if mask_secrets and self._is_sensitive(fld.name) and value:
                value = "****"
            result[fld.name] = value
        return result

    # ── Internals ──────────────────────────────────────────────────────

    def _apply_env_overrides(self) -> None:
        """Override fields with BUILDERPULSE_* env vars if present."""
        for fld in fields(self):
            env_name = _ENV_PREFIX + fld.name.upper()
            env_val = os.environ.get(env_name)
            if env_val is not None:
                # P1 fix: resolve string annotations to actual types
                import typing
                try:
                    hints = typing.get_type_hints(type(self))
                    fld_type = hints.get(fld.name, str)
                    # Handle Optional[X] → extract X
                    if hasattr(fld_type, "__origin__"):
                        args = fld_type.__args__
                        if args:
                            fld_type = args[0]
                except Exception:
                    fld_type = str

                if fld_type is bool:
                    setattr(self, fld.name, env_val.lower() in ("1", "true", "yes"))
                elif fld_type is int:
                    setattr(self, fld.name, int(env_val))
                else:
                    setattr(self, fld.name, env_val)

    @staticmethod
    def _is_sensitive(field_name: str) -> bool:
        """Check if a field name matches any SENSITIVE_KEYS entry.

        Comparison is case-insensitive; underscores are stripped so
        'telegram_bot_token' matches 'botToken'.
        """
        normalised = field_name.replace("_", "").lower()
        for key in SENSITIVE_KEYS:
            if key.replace("_", "").lower() in normalised:
                return True
        return False
