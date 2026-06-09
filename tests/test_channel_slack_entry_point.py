"""Self-test for Slack channel entry-point conformance (Task 18).

This file lives in the feature branch and tests the channel's protocol
conformance directly (import + isinstance). The full entry-point round-trip
(setuptools packaging + PluginRegistry.load) is verified by CI's
``scripts/check_entry_points_sorted.py`` plus integration tests, and by
the registration batch in Task 23.
"""

from __future__ import annotations


def test_slack_entry_point_self_check():
    """Self-test: module loads and satisfies ChannelPlugin Protocol."""
    from builderpulse.deliver.slack import SlackChannel
    from builderpulse.plugins.registry import ChannelPlugin

    # Use isinstance (not issubclass) — Protocol has non-method members
    ch = SlackChannel()
    assert isinstance(ch, ChannelPlugin)
    # Required attributes
    assert SlackChannel.name == "slack"
    assert SlackChannel.__experimental__ is False
    assert hasattr(SlackChannel, "deliver")
    assert hasattr(SlackChannel, "health_check")
    # health_check is a no-cost probe
    assert ch.health_check() is False  # no webhook_url configured by default
