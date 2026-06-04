"""Tests for the plugin registry system."""
import pytest
from unittest.mock import Mock, patch

from builderpulse.plugins.registry import PluginRegistry, DownloaderPlugin


class TestPluginRegistry:
    """Core PluginRegistry behavior."""

    def test_list_plugins_empty_group(self):
        """list_plugins on an empty/unknown group returns {}."""
        reg = PluginRegistry()
        assert reg.list_plugins("downloaders") == {}

    def test_get_plugin_unknown_returns_none(self):
        """get_plugin for a nonexistent name returns None."""
        reg = PluginRegistry()
        assert reg.get_plugin("downloaders", "nonexistent") is None

    def test_load_report_initially_empty(self):
        """get_load_report starts with empty lists for all groups."""
        reg = PluginRegistry()
        report = reg.get_load_report()
        assert all(v == [] for v in report.values())

    def test_register_dynamic_group(self):
        """register_group adds a new entry-point group."""
        PluginRegistry.register_group("custom", "myplugin.group")
        assert "custom" in PluginRegistry._ENTRY_POINT_GROUPS

    def test_validate_plugin_missing_methods(self):
        """_validate_plugin rejects an object missing required methods."""
        reg = PluginRegistry()
        incomplete = Mock(spec=[])
        assert reg._validate_plugin("downloaders", incomplete) is False

    def test_validate_plugin_valid(self):
        """_validate_plugin accepts an object satisfying DownloaderPlugin."""
        reg = PluginRegistry()
        valid = Mock()
        valid.name = "test"
        valid.can_handle = Mock(return_value=True)
        valid.download = Mock()
        assert isinstance(valid, DownloaderPlugin)
        assert reg._validate_plugin("downloaders", valid) is True

    def test_register_and_get_plugin(self):
        """Manually registered plugin is retrievable via get_plugin."""
        reg = PluginRegistry()
        plugin = Mock()
        plugin.name = "mydl"
        plugin.can_handle = Mock(return_value=True)
        plugin.download = Mock()
        reg.register("downloaders", plugin)
        assert reg.get_plugin("downloaders", "mydl") is plugin

    def test_register_rejects_invalid_plugin(self):
        """register raises ValueError for an invalid plugin."""
        reg = PluginRegistry()
        bad = Mock(spec=[])
        with pytest.raises(ValueError, match="does not satisfy"):
            reg.register("downloaders", bad)

    def test_get_load_report_tracks_errors(self):
        """get_load_report reflects any _load_errors that were recorded."""
        reg = PluginRegistry()
        reg._load_errors["downloaders"].append("bad_plugin: boom")
        report = reg.get_load_report()
        assert "bad_plugin: boom" in report["downloaders"]
