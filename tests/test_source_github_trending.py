"""Tests for GitHubTrendingSource (v2.1.0 Batch 1, Task 13).

Covers:
- HTML parsing of GitHub Trending page
- Circuit breaker fall-back to Search API when Trending yields 0 items
- Releases sub-feature when repos are configured
- No Releases API calls when repos=[] (zero-cost when unused)
- github_token never appears in logs (log sanitization)
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
import respx

from builderpulse.sources.github_trending import GitHubTrendingSource


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "github_trending" / "v1.html"


@pytest.fixture
def github_source():
    return GitHubTrendingSource(
        languages=["python"],
        since="daily",
        rate_limit_seconds=0,  # disable in tests
        repos=["anthropics/anthropic-cookbook"],
        github_token=None,
    )


def test_fetch_trending_html_parses_articles(github_source):
    """Parse GitHub trending HTML fixture, return FeedItem list with URLs."""
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    with respx.mock(base_url="https://github.com") as mock:
        mock.get("/trending/python").mock(return_value=httpx.Response(200, text=html))
        # Also mock releases for the configured repo
        with respx.mock(base_url="https://api.github.com") as api_mock:
            api_mock.get("/repos/anthropics/anthropic-cookbook/releases").mock(
                return_value=httpx.Response(200, json=[])
            )
            items = github_source.fetch()

    assert len(items) > 0
    # First set of items should be the trending ones (trending | search)
    trending_items = [
        i for i in items if i.metadata.get("sub_source") in ("trending", "search")
    ]
    assert len(trending_items) > 0
    assert all(item.url.startswith("https://github.com/") for item in trending_items)
    assert all(item.metadata.get("sub_source") == "trending" for item in trending_items)


def test_circuit_breaker_falls_back_to_search_api(github_source):
    """When Trending HTML yields 0 items, fall back to GitHub Search API."""
    empty_html = "<html><body>no articles</body></html>"
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://github.com/trending/python").mock(
            return_value=httpx.Response(200, text=empty_html)
        )
        mock.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "full_name": "anthropics/anthropic-cookbook",
                            "html_url": "https://github.com/anthropics/anthropic-cookbook",
                            "stargazers_count": 12345,
                        }
                    ]
                },
            )
        )
        mock.get(
            "https://api.github.com/repos/anthropics/anthropic-cookbook/releases"
        ).mock(return_value=httpx.Response(200, json=[]))
        items = github_source.fetch()

    search_items = [i for i in items if i.metadata.get("sub_source") == "search"]
    assert len(search_items) >= 1
    assert search_items[0].url == "https://github.com/anthropics/anthropic-cookbook"


def test_releases_subfeature_when_repos_configured(github_source):
    """When repos non-empty, fetch releases for each."""
    with respx.mock(assert_all_called=False) as mock:
        # Mock trending to be empty (so we focus on releases)
        mock.get("https://github.com/trending/python").mock(
            return_value=httpx.Response(
                200, text="<html><body>no articles</body></html>"
            )
        )
        mock.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        mock.get("/repos/anthropics/anthropic-cookbook/releases").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "tag_name": "v1.0",
                        "html_url": "https://github.com/anthropics/anthropic-cookbook/releases/tag/v1.0",
                        "published_at": "2026-06-01T00:00:00Z",
                        "name": "v1.0 release",
                    }
                ],
            )
        )
        items = github_source.fetch()

    releases_items = [i for i in items if i.metadata.get("sub_source") == "releases"]
    assert len(releases_items) == 1
    assert releases_items[0].url == (
        "https://github.com/anthropics/anthropic-cookbook/releases/tag/v1.0"
    )
    assert releases_items[0].published_at == "2026-06-01T00:00:00Z"


def test_no_releases_when_repos_empty():
    """If repos=[], skip Releases sub-feature (no API calls)."""
    src = GitHubTrendingSource(
        languages=["python"],
        since="daily",
        rate_limit_seconds=0,
        repos=[],
        github_token=None,
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://github.com/trending/python").mock(
            return_value=httpx.Response(
                200, text="<html><body>no articles</body></html>"
            )
        )
        mock.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        src.fetch()
        releases_calls = [c for c in mock.calls if "/releases" in str(c.request.url)]
    assert len(releases_calls) == 0


def test_log_sanitization_for_github_token(caplog):
    """github_token never appears in logs."""
    src = GitHubTrendingSource(
        languages=["python"],
        since="daily",
        rate_limit_seconds=0,
        repos=[],
        github_token="SECRET_TOKEN_xyz",
    )
    caplog.set_level(logging.DEBUG, logger="builderpulse.sources.github_trending")
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://github.com/trending/python").mock(
            return_value=httpx.Response(
                200, text="<html><body>no articles</body></html>"
            )
        )
        mock.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        src.fetch()

    for record in caplog.records:
        assert "SECRET_TOKEN_xyz" not in record.getMessage(), (
            f"Token leaked in log: {record.getMessage()!r}"
        )
