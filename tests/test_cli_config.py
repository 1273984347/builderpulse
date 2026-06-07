"""Tests for the `bp config` CLI subcommands (Week 0, Task 10).

Covers:
    - `bp config show` emits the "Newly available integrations" section
    - `bp config migrate` (no flag) reports the target version
    - `bp config migrate --interactive` declines gracefully when no plugins exist
    - `bp config migrate` handles a missing config file with a clear error
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from builderpulse.cli import cli
from builderpulse.core.config import TARGET_CONFIG_VERSION
from builderpulse.core.config_manager import ConfigManager


# ── Helpers ─────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_config_path(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ConfigManager to a temp config file and seed it with content."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"language": "en", "engine": "auto"}),
        encoding="utf-8",
    )
    ConfigManager.set_config_path(cfg_path)
    yield cfg_path
    # Reset so subsequent tests don't see the temp path.
    ConfigManager.set_config_path(Path.home() / ".builderpulse" / "config.json")


@pytest.fixture
def missing_config_path(tmp_path: Path, monkeypatch) -> Path:
    """Point ConfigManager at a path that does NOT exist (for missing-file test)."""
    cfg_path = tmp_path / "does_not_exist.json"
    if cfg_path.exists():
        cfg_path.unlink()
    ConfigManager.set_config_path(cfg_path)
    yield cfg_path
    ConfigManager.set_config_path(Path.home() / ".builderpulse" / "config.json")


# ── test_config_show_includes_newly_available_section ───────────────────


def test_config_show_includes_newly_available_section(tmp_config_path: Path, monkeypatch):
    """`bp config show` should always emit a 'Newly available' section header,
    even when no new integrations are installed in the current environment."""
    # Mock the registry to simulate the "no new plugins" state regardless of
    # what's actually installed in the env (e.g. github_trending in v2.1.0).
    from builderpulse.plugins import registry as reg_mod

    class _EmptyRegistry:
        def list_all(self, group):
            return {}

    monkeypatch.setattr(reg_mod, "PluginRegistry", _EmptyRegistry)

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0, result.output
    # The section header is always present (spec §3.6 — discoverability).
    assert "Newly available" in result.output
    # When no entry points are loaded, the body should explicitly say "(none)".
    assert "(none)" in result.output


def test_config_show_includes_full_config_dump(tmp_config_path: Path):
    """`bp config show` should still dump the full config (JSON body)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    # Core fields from the v2.1.0 dataclass should appear.
    assert "__version__" in result.output
    assert "enabled_sources" in result.output
    assert "enabled_channels" in result.output


# ── test_config_migrate_dry_run ─────────────────────────────────────────


def test_config_migrate_dry_run(tmp_config_path: Path):
    """`bp config migrate` (no --interactive) reports the target version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "migrate"])
    assert result.exit_code == 0, result.output
    # Should mention the version it migrated to and the path.
    assert "Config migrated" in result.output
    assert TARGET_CONFIG_VERSION in result.output
    assert str(tmp_config_path) in result.output
    # Should hint at the interactive option.
    assert "--interactive" in result.output


def test_config_migrate_missing_file(missing_config_path: Path):
    """`bp config migrate` on a missing config file exits non-zero with a clear error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "migrate"])
    assert result.exit_code != 0
    assert "config" in result.output.lower() or "init" in result.output.lower()


# ── test_config_migrate_interactive_no_plugins ──────────────────────────


def test_config_migrate_interactive_no_plugins(tmp_config_path: Path, monkeypatch):
    """When no entry-point plugins are loaded, --interactive should report
    "Nothing to migrate" rather than prompt for non-existent items."""
    # Mock the registry to simulate the "no new plugins" state regardless of
    # what's actually installed in the env (e.g. github_trending in v2.1.0).
    from builderpulse.plugins import registry as reg_mod

    class _EmptyRegistry:
        def list_all(self, group):
            return {}

    monkeypatch.setattr(reg_mod, "PluginRegistry", _EmptyRegistry)

    runner = CliRunner()
    # No input — the command should print the early-exit message without
    # ever calling click.confirm().
    result = runner.invoke(cli, ["config", "migrate", "--interactive"], input="")
    assert result.exit_code == 0, result.output
    # Either "Nothing to migrate" or "Found 0 new" is acceptable.
    assert "Nothing to migrate" in result.output or "Found 0 new" in result.output


# ── test_config_migrate_interactive_decline_all ─────────────────────────


def test_config_migrate_interactive_decline_all(tmp_config_path: Path, monkeypatch):
    """When new plugins exist (mocked) but user declines all, file is unchanged.

    We mock ``PluginRegistry.list_all`` to return a couple of "new" entries,
    then feed ``n`` to every prompt. The command should report "No changes".
    """
    from builderpulse.plugins import registry as reg_mod

    class FakeRegistry:
        def list_all(self, group):
            if group == "sources":
                return {"github_trending": None, "twitch": None}
            if group == "channels":
                return {"slack": None, "notion": None}
            return {}

    monkeypatch.setattr(reg_mod, "PluginRegistry", FakeRegistry)
    # Also patch the import inside the cli module (already imported there
    # lazily, so patching the source module is sufficient).

    runner = CliRunner()
    # Feed 'n' for every prompt (2 sources + 2 channels = 4 prompts).
    result = runner.invoke(
        cli,
        ["config", "migrate", "--interactive"],
        input="n\nn\nn\nn\n",
    )
    assert result.exit_code == 0, result.output
    # Should report the discovered count and that nothing was changed.
    assert "2 new sources" in result.output
    assert "2 new channels" in result.output
    assert "No changes made" in result.output or "No changes" in result.output

    # File should NOT have been modified beyond the auto-migration (enabled_sources
    # still does NOT contain github_trending or twitch).
    raw = json.loads(tmp_config_path.read_text(encoding="utf-8"))
    assert "github_trending" not in raw.get("enabled_sources", [])
    assert "twitch" not in raw.get("enabled_sources", [])
    assert "slack" not in raw.get("enabled_channels", [])


# ── test_config_migrate_interactive_accept_some ─────────────────────────


def test_config_migrate_interactive_accept_some(tmp_config_path: Path, monkeypatch):
    """When user accepts some prompts, those entries get appended and persisted.

    Mocks the registry to return two new sources; user accepts the first,
    declines the second. The config file should be updated accordingly.
    """
    from builderpulse.plugins import registry as reg_mod

    class FakeRegistry:
        def list_all(self, group):
            if group == "sources":
                return {"github_trending": None, "twitch": None}
            if group == "channels":
                return {}
            return {}

    monkeypatch.setattr(reg_mod, "PluginRegistry", FakeRegistry)

    runner = CliRunner()
    # First prompt: y (accept github_trending). Second: n (decline twitch).
    result = runner.invoke(
        cli,
        ["config", "migrate", "--interactive"],
        input="y\nn\n",
    )
    assert result.exit_code == 0, result.output

    raw = json.loads(tmp_config_path.read_text(encoding="utf-8"))
    assert "github_trending" in raw.get("enabled_sources", [])
    assert "twitch" not in raw.get("enabled_sources", [])
    # File should still have __version__ set to the target.
    assert raw.get("__version__") == TARGET_CONFIG_VERSION
