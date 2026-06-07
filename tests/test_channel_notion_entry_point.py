"""Self-test for Notion channel entry-point conformance (Task 19).

This file lives in the feature branch and tests the channel's protocol
conformance directly (import + isinstance). The full entry-point
round-trip (setuptools packaging + PluginRegistry.load) is verified by
CI's ``scripts/check_entry_points_sorted.py`` plus integration tests,
and by the registration batch in Task 23.
"""

from __future__ import annotations


def test_notion_entry_point_self_check():
    """Self-test: module loads and satisfies ChannelPlugin Protocol."""
    from builderpulse.deliver.notion import NotionChannel
    from builderpulse.deliver.notion_page import NotionPage
    from builderpulse.plugins.registry import ChannelPlugin

    # Use isinstance (not issubclass) — Protocol has non-method members
    ch = NotionChannel(token="x", database_id="y")
    assert isinstance(ch, ChannelPlugin)

    # Required attributes
    assert NotionChannel.name == "notion"
    assert NotionChannel.__experimental__ is False
    assert hasattr(NotionChannel, "deliver")
    assert hasattr(NotionChannel, "health_check")

    # health_check is a no-cost probe
    assert ch.health_check() is True  # both token + db configured

    # Default construction: no token/db → health_check is False
    ch_default = NotionChannel()
    assert ch_default.health_check() is False

    # NotionPage dataclass is importable + has the serializer
    p = NotionPage(title="X", tags=["a"])
    props = p.to_notion_properties()
    assert "Name" in props
    assert "Tags" in props
