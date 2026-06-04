"""Thread-safe ConfigManager singleton with hot-reload and subscriber notifications.

Wraps Config.from_file() with:
  - Double-checked locking for safe concurrent access
  - Hot-reload with reentrancy protection
  - Subscriber notifications on config changes
  - File permission checks (warns on group/other access)
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
from pathlib import Path
from typing import Callable, Optional

from builderpulse.core.config import Config

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = str(Path.home() / ".builderpulse" / "config.json")


class ConfigManager:
    """Thread-safe singleton for BuilderPulse configuration.

    All state is held as class variables — there is no instance.
    Thread safety is achieved via a class-level ``threading.RLock``.
    """

    _lock: threading.RLock = threading.RLock()
    _reload_lock: threading.Lock = threading.Lock()  # P1 fix: serialise concurrent reloads
    _config: Optional[Config] = None
    _subscribers: list[Callable[[Config], None]] = []
    _reloading: bool = False
    _default_path: str = _DEFAULT_CONFIG_PATH
    _instance_path: Optional[str] = None
    _failed_callbacks: list[dict] = []

    # ── Path management ──────────────────────────────────────────────────

    @classmethod
    def get_config_path(cls) -> str:
        """Return the resolved config path.

        Priority:
            1. ``_instance_path`` (set via :meth:`set_config_path`)
            2. ``BUILDERPULSE_CONFIG_PATH`` env var
            3. ``_default_path``
        """
        with cls._lock:
            if cls._instance_path is not None:
                return cls._instance_path
            return os.environ.get("BUILDERPULSE_CONFIG_PATH", cls._default_path)

    @classmethod
    def set_config_path(cls, path: str | Path) -> None:
        """Set the config file path and invalidate cached config."""
        with cls._lock:
            cls._instance_path = str(path)
            cls._config = None  # force reload on next get()

    # ── Core access ──────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> Config:
        """Return the current Config, loading it on first access."""
        with cls._lock:
            if cls._config is not None:
                return cls._config

            path = cls.get_config_path()
            cls._check_config_permissions(path)
            cls._config = Config.from_file(path)
            return cls._config

    @classmethod
    def get_raw(cls) -> dict:
        """Return the raw JSON config as a dict (includes fields not in Config dataclass)."""
        path = cls.get_config_path()
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @classmethod
    def reload(cls) -> Config:
        """Reload config from disk and notify subscribers.

        Uses _reload_lock to serialise concurrent reloads. Reentrancy guard
        prevents recursive reloads via subscriber callbacks.
        """
        with cls._reload_lock:  # P1 fix: serialise concurrent reloads
            with cls._lock:
                if cls._reloading:
                    return cls._config or Config.from_defaults()

                cls._reloading = True
                cls._failed_callbacks.clear()
                try:
                    path = cls.get_config_path()
                    # P1 fix: catch FileNotFoundError when config is deleted
                    try:
                        new_config = Config.from_file(path)
                    except FileNotFoundError:
                        logger.warning("Config file not found at %s, keeping cached config", path)
                        cls._reloading = False
                        return cls._config or Config.from_defaults()
                    cls._config = new_config
                    subs = cls._subscribers.copy()
                finally:
                    cls._reloading = False  # Reset BEFORE calling callbacks

            for cb in subs:
                try:
                    cb(new_config)
                except Exception as exc:
                    with cls._lock:
                        cls._failed_callbacks.append(
                            {"callback": repr(cb), "error": str(exc)}
                        )
                    logger.warning("Subscriber callback failed: %s", exc)

            return new_config

    # ── Subscribers ──────────────────────────────────────────────────────

    @classmethod
    def subscribe(cls, callback: Callable[[Config], None]) -> None:
        """Register a callback to be notified on config reload."""
        with cls._lock:
            cls._subscribers.append(callback)

    @classmethod
    def get_failed_callbacks(cls) -> list[dict]:
        """Return a copy of callbacks that failed during the last reload."""
        with cls._lock:
            return list(cls._failed_callbacks)

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _check_config_permissions(path: str) -> None:
        """Warn if the config file is group/other readable or writable."""
        try:
            st = os.stat(path)
            mode = st.st_mode
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                logger.warning(
                    "Config file %s has overly permissive permissions "
                    "(group/other access detected). Consider: chmod 600 %s",
                    path,
                    path,
                )
        except OSError:
            # File may not exist yet — Config.from_file will raise if needed
            pass
