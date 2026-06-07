"""Self-test for twitch source entry-point registration (Task 14).

This file lives in the feature branch and tests the source's protocol
conformance directly (import + isinstance). The full entry-point round-trip
(setuptools packaging + PluginRegistry.load) is verified by CI's
``scripts/check_entry_points_sorted.py`` plus integration tests, and by
the registration batch in Task 23.
"""
from __future__ import annotations


def test_twitch_entry_point_self_check():
    """Self-test: module loads and satisfies SourcePlugin Protocol."""
    from builderpulse.plugins.registry import SourcePlugin
    from builderpulse.sources.twitch import TwitchSource

    instance = TwitchSource(
        client_id="x", client_secret="y", channel_logins=["anthropic"]
    )
    # Protocol conformance (runtime_checkable; isinstance supports non-method members)
    assert isinstance(instance, SourcePlugin)
    # Required attributes
    assert TwitchSource.name == "twitch"
    assert TwitchSource.__experimental__ is False
    assert hasattr(TwitchSource, "fetch")
    assert hasattr(TwitchSource, "health_check")
    # health_check is a no-cost probe (does not call Twitch)
    assert instance.health_check() is True
