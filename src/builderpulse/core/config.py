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

# Target config schema version. Bump when fields are added/renamed.
# `__version__` uses simple string comparison because BuilderPulse versions
# follow strict X.Y.Z format where lexicographic order == semantic order
# (e.g., "2.10.0" >= "2.1.0"). See spec §3.6.
TARGET_CONFIG_VERSION = "2.1.0"

# v2.0.0 sources: enabled by default on v2.0.0 → v2.1.0 migration
_DEFAULT_ENABLED_SOURCES = [
    "bilibili",
    "youtube",
    "podcast",
    "blog",
    "twitter",
]

# v2.0.0 channels: enabled by default on v2.0.0 → v2.1.0 migration
_DEFAULT_ENABLED_CHANNELS = [
    "telegram",
    "email",
    "lark",
    "dingtalk",
    "discord",
    "wecom",
    "wechat",
    "stderr",
]

SENSITIVE_KEYS = frozenset(
    {
        "botToken",
        "apiKey",
        "apiSecret",
        "sessdata",
        "password",
        "secret",
    }
)

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

    # v2.1.0 additions (per spec §3.6). The Python field ``version`` maps to
    # the JSON key ``__version__`` (see from_file/to_dict); the leading-underscore
    # form is reserved by Python's name-mangling rules but is the canonical
    # name in the on-disk config file.
    version: str = TARGET_CONFIG_VERSION
    enabled_sources: list = field(
        default_factory=lambda: list(_DEFAULT_ENABLED_SOURCES)
    )
    enabled_channels: list = field(
        default_factory=lambda: list(_DEFAULT_ENABLED_CHANNELS)
    )
    sources_config: dict = field(default_factory=dict)
    channels_config: dict = field(default_factory=dict)

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

        Migration (per spec §3.6):
            - If ``__version__`` is missing or < ``TARGET_CONFIG_VERSION``,
              fill in ``enabled_sources`` / ``enabled_channels`` with the
              v2.0.0 defaults and write ``__version__`` back to disk. This is
              idempotent — once the file is at the target version, future
              loads do not touch the user's values.
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # ── v2.0.0 → v2.1.0 migration ────────────────────────────────
        raw_version = data.get("__version__", "")
        if not raw_version or raw_version < TARGET_CONFIG_VERSION:
            data.setdefault("enabled_sources", list(_DEFAULT_ENABLED_SOURCES))
            data.setdefault("enabled_channels", list(_DEFAULT_ENABLED_CHANNELS))
            data["__version__"] = TARGET_CONFIG_VERSION
            # Persist migration so subsequent loads skip the default-fill.
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        # Translate the on-disk key ``__version__`` into the Python field
        # ``version`` (avoids name-mangling on the dataclass).
        if "__version__" in data and "version" not in data:
            data["version"] = data["__version__"]

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

        The ``version`` field is written out as ``__version__`` to match
        the on-disk JSON convention (spec §3.6).
        """
        result = {}
        for fld in fields(self):
            value = getattr(self, fld.name)
            if mask_secrets and self._is_sensitive(fld.name) and value:
                value = "****"
            if fld.name == "version":
                result["__version__"] = value
            else:
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
