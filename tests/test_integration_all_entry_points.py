"""Integration test: verify all entry_points load and satisfy Protocol.

This is the registration batch verification (per spec §5.5). After this
PR merges, every source/channel in the codebase is registered via
entry_points and discoverable by ``PluginRegistry.discover()``.

These tests do NOT depend on which PRs have been merged — they just
verify the entry_points registered in ``pyproject.toml`` can be loaded
and the classes satisfy the runtime-checkable Protocol.
"""

from __future__ import annotations

import sys
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def source_entry_points() -> dict[str, EntryPoint]:
    """Return all source entry_points registered in pyproject.toml."""
    eps = entry_points(group="builderpulse.sources")
    return {ep.name: ep for ep in eps}


@pytest.fixture(scope="module")
def channel_entry_points() -> dict[str, EntryPoint]:
    """Return all channel entry_points registered in pyproject.toml."""
    eps = entry_points(group="builderpulse.channels")
    return {ep.name: ep for ep in eps}


# ---------------------------------------------------------------------------
# Registration completeness
# ---------------------------------------------------------------------------


def test_all_9_sources_registered(source_entry_points: dict[str, EntryPoint]) -> None:
    """9 sources must be registered: 5 v2.0.0 + 4 v2.1.0."""
    expected = {
        # v2.0.0
        "bilibili",
        "blog",
        "podcast",
        "twitter",
        "youtube",
        # v2.1.0
        "github_trending",
        "twitch",
        "wechat_mp",
        "xiaohongshu",
    }
    actual = set(source_entry_points.keys())
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"Missing source entry_points: {sorted(missing)}"
    assert not extra, f"Unexpected source entry_points: {sorted(extra)}"


def test_all_12_channels_registered(
    channel_entry_points: dict[str, EntryPoint],
) -> None:
    """12 channels must be registered: 8 v2.0.0 + 4 v2.1.0.

    Note: the v2.0.0 channel file ``lark.py`` registers under the
    entry_point name ``lark`` (matching the manual ``_CHANNELS`` registry
    in ``src/builderpulse/deliver/__init__.py``). Earlier design specs
    suggested ``feishu`` but the actual code uses ``lark``.
    """
    expected = {
        # v2.0.0
        "dingtalk",
        "discord",
        "email",
        "lark",
        "stderr",
        "telegram",
        "wechat",
        "wecom",
        # v2.1.0
        "bark",
        "notion",
        "slack",
        "webhook",
    }
    actual = set(channel_entry_points.keys())
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"Missing channel entry_points: {sorted(missing)}"
    assert not extra, f"Unexpected channel entry_points: {sorted(extra)}"


# ---------------------------------------------------------------------------
# Protocol conformance (entry_point classes)
# ---------------------------------------------------------------------------


def test_all_sources_satisfy_protocol(
    source_entry_points: dict[str, EntryPoint],
) -> None:
    """Each source entry_point's class satisfies SourcePlugin Protocol.

    Loads each class via ``EntryPoint.load()`` and asserts the
    ``is_source_plugin_compatible`` helper returns True.
    """
    from builderpulse.plugins.registry import is_source_plugin_compatible

    for name, ep in source_entry_points.items():
        cls = ep.load()
        assert is_source_plugin_compatible(cls), (
            f"Source {name!r} ({cls.__module__}.{cls.__name__}) does not "
            f"satisfy SourcePlugin Protocol (missing 'name' or 'fetch')"
        )


def test_all_channels_satisfy_protocol(
    channel_entry_points: dict[str, EntryPoint],
) -> None:
    """Each channel entry_point's class satisfies ChannelPlugin Protocol.

    Loads each class via ``EntryPoint.load()`` and asserts the
    ``is_channel_plugin_compatible`` helper returns True.
    """
    from builderpulse.plugins.registry import is_channel_plugin_compatible

    for name, ep in channel_entry_points.items():
        cls = ep.load()
        assert is_channel_plugin_compatible(cls), (
            f"Channel {name!r} ({cls.__module__}.{cls.__name__}) does not "
            f"satisfy ChannelPlugin Protocol (missing 'name' or 'deliver')"
        )


# ---------------------------------------------------------------------------
# Alphabetical sort (matches CI script)
# ---------------------------------------------------------------------------


def test_entry_points_alphabetically_sorted() -> None:
    """``pyproject.toml`` entry_points must be sorted alphabetically.

    Mirrors ``scripts/check_entry_points_sorted.py`` and is enforced as a
    CI gate (per design spec §5.1). The script also runs in CI; this test
    catches regressions faster in the unit test suite.
    """
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - 3.9/3.10 fallback
        import tomli as tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    entry_points_section = data.get("project", {}).get("entry-points", {})
    for group, entries in entry_points_section.items():
        names = list(entries.keys())
        assert names == sorted(names), (
            f"entry_points in {group!r} not sorted: {names} (expected {sorted(names)})"
        )
