"""Self-test for github_trending source entry-point registration (Task 13).

This file lives in the feature branch and tests the source's protocol
conformance directly (import + isinstance). The full entry-point round-trip
(setuptools packaging + PluginRegistry.load) is verified by the registration
batch in Task 23 — see the v2.1.0 roadmap design doc.
"""

from __future__ import annotations


def test_github_trending_entry_point_self_check():
    """Self-test: module loads and satisfies SourcePlugin Protocol."""
    from builderpulse.plugins.registry import SourcePlugin
    from builderpulse.sources.github_trending import GitHubTrendingSource

    instance = GitHubTrendingSource(languages=["python"], rate_limit_seconds=0)
    # Protocol conformance (runtime_checkable; isinstance supports non-method members)
    assert isinstance(instance, SourcePlugin)
    # Required attributes
    assert GitHubTrendingSource.name == "github_trending"
    assert hasattr(GitHubTrendingSource, "fetch")
    assert hasattr(GitHubTrendingSource, "health_check")
    # health_check is a no-cost probe (does not call GitHub)
    assert instance.health_check() is True
