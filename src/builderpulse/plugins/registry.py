"""Plugin registry with lazy entry-point loading and Protocol validation.

Design goals:
- Fault-tolerant: one bad plugin never breaks others or the host.
- Lazy: entry points are resolved on first access, not at import time.
- Extensible: new plugin groups can be registered at runtime.
"""
from __future__ import annotations

import logging
import threading
from importlib.metadata import entry_points
from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol interfaces (runtime-checkable so isinstance works)
# ---------------------------------------------------------------------------

@runtime_checkable
class DownloaderPlugin(Protocol):
    """A plugin that can download content from a URL."""

    name: str

    def can_handle(self, url: str) -> bool: ...
    def download(self, url: str, output_dir: str, **kwargs: Any) -> Any: ...


@runtime_checkable
class SourcePlugin(Protocol):
    """A plugin that provides a content source."""

    name: str

    def fetch(self, **kwargs: Any) -> Any: ...


@runtime_checkable
class ChannelPlugin(Protocol):
    """A plugin that delivers content to a channel."""

    name: str

    def deliver(self, content: Any, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Group -> Protocol mapping
# ---------------------------------------------------------------------------

_PROTOCOLS: Dict[str, type] = {
    "downloaders": DownloaderPlugin,
    "sources": SourcePlugin,
    "channels": ChannelPlugin,
}


# ---------------------------------------------------------------------------
# Plugin Registry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Central registry for entry-point-based plugins.

    Thread-safe, lazy-loading, fault-tolerant.
    """

    # Maps group names -> entry_point group strings
    _ENTRY_POINT_GROUPS: Dict[str, str] = {
        "downloaders": "builderpulse.downloaders",
        "sources": "builderpulse.sources",
        "channels": "builderpulse.channels",
    }

    def __init__(self) -> None:
        self._plugins: Dict[str, Dict[str, Any]] = {}
        self._load_errors: Dict[str, List[str]] = {
            g: [] for g in self._ENTRY_POINT_GROUPS
        }
        self._loaded_groups: Set[str] = set()
        self._lock = threading.Lock()

    # -- class-level helpers -------------------------------------------------

    @classmethod
    def register_group(cls, group: str, entry_point_group: str) -> None:
        """Register a new plugin group at class level.

        This affects all *future* PluginRegistry instances (and the module-level
        singleton after it is recreated).  Existing instances that have already
        cached ``_ENTRY_POINT_GROUPS`` will see the update because we mutate
        the class dict directly.
        """
        cls._ENTRY_POINT_GROUPS[group] = entry_point_group
        # Also register a permissive Protocol if none exists yet
        if group not in _PROTOCOLS:
            # Create a catch-all Protocol so validation doesn't crash
            _PROTOCOLS[group] = DownloaderPlugin  # type: ignore[assignment]

    # -- lazy loading --------------------------------------------------------

    def _ensure_loaded(self, group: str) -> None:
        """Load entry points for *group* if not already done (thread-safe)."""
        if group in self._loaded_groups:
            return
        with self._lock:
            # Double-check after acquiring lock
            if group in self._loaded_groups:
                return

            self._load_errors.setdefault(group, [])

            ep_group_str = self._ENTRY_POINT_GROUPS.get(group)
            if ep_group_str is None:
                # Unknown group — nothing to load
                self._loaded_groups.add(group)
                return

            self._plugins.setdefault(group, {})

            try:
                eps = entry_points(group=ep_group_str)
            except Exception as exc:
                msg = f"[{group}] entry_points lookup failed: {exc}"
                logger.warning(msg)
                self._load_errors[group].append(msg)
                self._loaded_groups.add(group)
                return

            for ep in eps:
                try:
                    obj = ep.load()
                    instance = obj() if callable(obj) and not isinstance(obj, type) else obj
                    if self._validate_plugin(group, instance):
                        name = getattr(instance, "name", ep.name)
                        self._plugins[group][name] = instance
                        logger.debug("Loaded plugin %s.%s", group, name)
                    else:
                        msg = (
                            f"{ep.name}: does not satisfy "
                            f"{_PROTOCOLS.get(group, 'unknown')} protocol"
                        )
                        logger.warning(msg)
                        self._load_errors[group].append(msg)
                except Exception as exc:
                    msg = f"{ep.name}: {exc}"
                    logger.warning("Failed to load plugin %s.%s: %s", group, ep.name, exc)
                    self._load_errors[group].append(msg)

            self._loaded_groups.add(group)

    # -- validation ----------------------------------------------------------

    def _validate_plugin(self, group: str, plugin: Any) -> bool:
        """Return True if *plugin* satisfies the Protocol for *group*.

        Uses ``isinstance`` with ``@runtime_checkable`` Protocol, which checks
        for the presence of required methods/attributes.
        """
        protocol = _PROTOCOLS.get(group)
        if protocol is None:
            # Unknown group — accept anything
            return True
        try:
            return isinstance(plugin, protocol)
        except Exception:
            return False

    # -- manual registration -------------------------------------------------

    def register(self, group: str, plugin: Any) -> None:
        """Register a plugin instance directly (bypasses entry points).

        Raises ``ValueError`` if the plugin doesn't satisfy the group's Protocol.
        """
        if not self._validate_plugin(group, plugin):
            protocol = _PROTOCOLS.get(group, "unknown")
            raise ValueError(
                f"Plugin {plugin!r} does not satisfy {protocol} protocol"
            )
        name = getattr(plugin, "name", repr(plugin))
        with self._lock:
            self._plugins.setdefault(group, {})[name] = plugin

    # -- public queries ------------------------------------------------------

    def list_plugins(self, group: str) -> Dict[str, Any]:
        """Return ``{name: instance}`` for all loaded plugins in *group*."""
        self._ensure_loaded(group)
        return dict(self._plugins.get(group, {}))

    def get_plugin(self, group: str, name: str) -> Optional[Any]:
        """Return a single plugin by group + name, or ``None``."""
        self._ensure_loaded(group)
        return self._plugins.get(group, {}).get(name)

    def get_load_report(self) -> Dict[str, List[str]]:
        """Return ``{group: [error_strings]}`` for all groups."""
        # Ensure all groups have been loaded so the report is complete
        for group in list(self._ENTRY_POINT_GROUPS):
            self._ensure_loaded(group)
        return {g: list(errs) for g, errs in self._load_errors.items()}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry = PluginRegistry()


def get_plugin(group: str, name: str) -> Optional[Any]:
    """Convenience: look up a plugin on the global registry."""
    return _registry.get_plugin(group, name)


def list_plugins(group: str) -> Dict[str, Any]:
    """Convenience: list plugins on the global registry."""
    return _registry.list_plugins(group)
