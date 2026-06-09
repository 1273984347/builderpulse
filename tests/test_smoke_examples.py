"""Smoke test examples — demonstrate the live-integration pattern.

Tests marked with ``@pytest.mark.smoke`` are picked up by the nightly
``smoke.yml`` workflow. They typically hit real external services
(Twitch, Notion, Slack, Bark, webhooks) and are skipped when the
corresponding ``SMOKE_*`` secret is absent.

See ``docs/smoke-secrets.md`` for the full list of required secrets.

For Week 0 this module exists primarily to:
1. Verify the smoke marker is registered and ``pytest -m smoke`` collects
   something (so the workflow has at least one test to run).
2. Provide copy-pasteable templates for Batch 1/2 integrations
   (Twitch VODs, Notion DB, Slack channel, Bark channel, generic webhook,
   GitHub Trending, Xiaohongshu, WeChat MP).
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.smoke
def test_smoke_marker_collects():
    """Sanity: the smoke marker is registered and this test is collected.

    This is the only smoke test that does NOT depend on external services
    or secrets, so it always runs and gives the nightly workflow a green
    baseline. If this test is missing or broken, the entire smoke
    infrastructure is broken.
    """
    assert os.environ.get("PATH"), "PATH must be set in any reasonable env"


@pytest.mark.smoke
def test_github_trending_smoke_live():
    """Smoke template: fetch 1 page from live GitHub Trending.

    The actual source module lands in Task 13. This test is skipped by
    default and only runs when ``BUILDERPULSE_SMOKE_GITHUB=1`` is set in
    the smoke workflow env (i.e. once Task 13 ships and the source
    imports cleanly).
    """
    if not os.environ.get("BUILDERPULSE_SMOKE_GITHUB"):
        pytest.skip(
            "Set BUILDERPULSE_SMOKE_GITHUB=1 to enable live GitHub Trending smoke"
        )
    # (Real call happens once GitHub source is implemented in Task 13)
    # For now, just verify the import works
    from builderpulse.sources.github_trending import GitHubTrendingSource

    assert GitHubTrendingSource.name == "github_trending"
