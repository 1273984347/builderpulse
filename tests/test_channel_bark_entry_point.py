"""Self-test for Bark channel entry-point conformance (Task 16).

This file lives in the feature branch and tests the channel's protocol
conformance directly (import + isinstance). The full entry-point round-trip
(setuptools packaging + PluginRegistry.load) is verified by CI's
``scripts/check_entry_points_sorted.py`` plus integration tests, and by
the registration batch in Task 23.
"""

from __future__ import annotations


def test_bark_entry_point_self_check():
    """Self-test: module loads and satisfies ChannelPlugin Protocol."""
    from builderpulse.deliver.bark import BarkChannel
    from builderpulse.plugins.registry import ChannelPlugin

    # Use isinstance (not issubclass) — Protocol has non-method members
    ch = BarkChannel()
    assert isinstance(ch, ChannelPlugin)
    # Required attributes
    assert BarkChannel.name == "bark"
    assert BarkChannel.__experimental__ is False
    assert hasattr(BarkChannel, "deliver")
    assert hasattr(BarkChannel, "health_check")
    # health_check is a no-cost probe
    assert ch.health_check() is False  # no device_key configured by default
