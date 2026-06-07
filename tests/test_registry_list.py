"""Tests for PluginRegistry.list() and list_all() extensions (Task 6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from builderpulse.plugins.registry import PluginRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeSource:
    """Minimal SourcePlugin duck-type: has ``name`` and ``fetch``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def fetch(self, **kwargs):  # pragma: no cover - never invoked
        return []

    def health_check(self) -> bool:  # pragma: no cover - never invoked
        return True


class _FakeDownloader:
    """Minimal DownloaderPlugin duck-type: has ``name``, ``can_handle``,
    ``download``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def can_handle(self, url: str) -> bool:  # pragma: no cover
        return True

    def download(self, url: str, output_dir: str, **kwargs):  # pragma: no cover
        return None


@pytest.fixture
def registry() -> PluginRegistry:
    return PluginRegistry()


# ---------------------------------------------------------------------------
# list(group) — backward-compatible behavior
# ---------------------------------------------------------------------------


def test_list_returns_all_loaded_by_default(registry: PluginRegistry) -> None:
    """list(group) without enabled_only returns all loaded plugins."""
    # Patch entry_points to return no auto-discovered sources (e.g. suppress
    # github_trending from v2.1.0) so this test stays hermetic.
    with patch(
        "builderpulse.plugins.registry.entry_points", return_value=[]
    ):
        registry.register("sources", _FakeSource("alpha"))
        registry.register("sources", _FakeSource("beta"))
        plugins = registry.list("sources")
    assert set(plugins.keys()) == {"alpha", "beta"}


def test_list_unknown_group_returns_empty(registry: PluginRegistry) -> None:
    """list on an unknown group returns {} (matches legacy list_plugins)."""
    assert registry.list("nonexistent_group") == {}


def test_list_plugins_alias_still_works(registry: PluginRegistry) -> None:
    """list_plugins() remains as a deprecated alias for v2.0.0 compat."""
    registry.register("sources", _FakeSource("alpha"))
    # Both spellings return the same result
    assert registry.list_plugins("sources") == registry.list("sources")


# ---------------------------------------------------------------------------
# list(group, enabled_only=True) — config-driven filtering
# ---------------------------------------------------------------------------


def test_list_with_enabled_only_filters_by_config(registry: PluginRegistry) -> None:
    """list(group, enabled_only=True) filters by config's enabled list."""
    registry.register("sources", _FakeSource("alpha"))
    registry.register("sources", _FakeSource("beta"))

    mock_config = MagicMock()
    mock_config.enabled_sources = ["alpha"]
    with patch(
        "builderpulse.core.config_manager.ConfigManager.get",
        return_value=mock_config,
    ):
        plugins = registry.list("sources", enabled_only=True)

    assert "alpha" in plugins
    assert "beta" not in plugins


def test_list_with_enabled_only_empty_config_returns_empty(
    registry: PluginRegistry,
) -> None:
    """When config's enabled list is empty, enabled_only returns {}."""
    registry.register("sources", _FakeSource("alpha"))

    mock_config = MagicMock()
    mock_config.enabled_sources = []
    with patch(
        "builderpulse.core.config_manager.ConfigManager.get",
        return_value=mock_config,
    ):
        plugins = registry.list("sources", enabled_only=True)

    assert plugins == {}


def test_list_enabled_only_unsupported_group_returns_all(
    registry: PluginRegistry,
) -> None:
    """Groups with no enabled_field mapping return all plugins unchanged."""
    registry.register("downloaders", _FakeDownloader("dl1"))
    # "downloaders" has no enabled_field mapping; should not even call ConfigManager
    with patch(
        "builderpulse.core.config_manager.ConfigManager.get"
    ) as mock_get:
        plugins = registry.list("downloaders", enabled_only=True)
    assert "dl1" in plugins
    mock_get.assert_not_called()


def test_list_enabled_only_config_error_falls_back_to_all(
    registry: PluginRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """If ConfigManager.get() raises, enabled_only logs warning and returns all."""
    registry.register("sources", _FakeSource("alpha"))

    with patch(
        "builderpulse.core.config_manager.ConfigManager.get",
        side_effect=RuntimeError("config broken"),
    ):
        with caplog.at_level("WARNING"):
            plugins = registry.list("sources", enabled_only=True)

    # Falls back gracefully to "return all"
    assert "alpha" in plugins
    assert any("enabled_only" in rec.message for rec in caplog.records)


def test_list_enabled_only_missing_config_field_returns_all(
    registry: PluginRegistry,
) -> None:
    """If the enabled field doesn't exist on Config, degrade to 'return all'.

    This protects users on v2.0.0 configs (which lack enabled_sources) from
    silently getting an empty plugin list.
    """
    registry.register("sources", _FakeSource("alpha"))

    mock_config = MagicMock(spec=[])  # no attributes at all
    with patch(
        "builderpulse.core.config_manager.ConfigManager.get",
        return_value=mock_config,
    ):
        plugins = registry.list("sources", enabled_only=True)

    assert "alpha" in plugins


# ---------------------------------------------------------------------------
# list_all(group) — full entry-point discovery (for 'bp config show')
# ---------------------------------------------------------------------------


def _fake_entry_points():
    """Build a pair of mock entry points; the second one fails to load.

    Using ``MagicMock`` rather than real ``EntryPoint`` objects avoids
    depending on importable module paths in the test layout.
    """
    loaded_ep = MagicMock()
    loaded_ep.name = "loaded_plugin"
    loaded_ep.load.return_value = _FakeSource("loaded_plugin")

    missing_ep = MagicMock()
    missing_ep.name = "missing_extra"
    missing_ep.load.side_effect = ImportError("No module named 'fake_extra'")

    return [loaded_ep, missing_ep]


def test_list_all_returns_entry_point_names(registry: PluginRegistry) -> None:
    """list_all(group) returns all entry_point names, including unloadable ones."""
    fake_eps = _fake_entry_points()
    with patch(
        "builderpulse.plugins.registry.entry_points", return_value=fake_eps
    ):
        result = registry.list_all("sources")
    # Both names must appear in the result, even if one couldn't be loaded
    assert "loaded_plugin" in result
    assert "missing_extra" in result


def test_list_all_marks_unloaded_as_none(registry: PluginRegistry) -> None:
    """Unloaded entry points (missing extras, etc.) are surfaced as None."""
    fake_eps = _fake_entry_points()
    with patch(
        "builderpulse.plugins.registry.entry_points", return_value=fake_eps
    ):
        result = registry.list_all("sources")
    # 'missing_extra' should be in the dict but its value should be None
    assert "missing_extra" in result
    assert result["missing_extra"] is None
    # The loadable one should have a real instance
    assert result["loaded_plugin"] is not None


def test_list_all_unknown_group_returns_empty(registry: PluginRegistry) -> None:
    """list_all on an unknown group returns {} (nothing to discover)."""
    assert registry.list_all("nonexistent_group") == {}
