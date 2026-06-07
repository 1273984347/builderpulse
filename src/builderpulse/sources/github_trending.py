"""GitHub Trending + Releases source (v2.1.0).

Combines three sub-features:
- Trending: HTML scraping of github.com/trending/{languages}?since={daily|weekly|monthly}
- Search API: circuit-breaker fall-back when Trending yields 0 items
- Releases: GitHub REST API for recent releases of configured repos

All items are returned as ``FeedItem`` with ``sub_source`` stored in ``metadata``
to distinguish the three pipelines (trending | search | releases).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger(__name__)

# Minimum sleep between any outbound HTTP call (seconds). Set to 0 in tests.
DEFAULT_RATE_LIMIT_SECONDS = 2

# Sub-source tags stored in FeedItem.metadata["sub_source"]
SUB_TRENDING = "trending"
SUB_SEARCH = "search"
SUB_RELEASES = "releases"


class GitHubTrendingSource:
    """Fetch GitHub Trending (HTML), Releases (API), and Search (API fall-back).

    The source is intentionally defensive: every sub-feature is wrapped in a
    try/except so one failure does not break the others. The Trending HTML
    scrape is the primary path; the Search API is a circuit-breaker fall-back
    for the 0-item case (e.g. empty page, parse error, or upstream changes).
    Releases are only fetched when ``repos`` is non-empty.
    """

    name = "github_trending"
    # Pinned at v2.1.0 — this source is stable (not experimental).
    __experimental__ = False

    def __init__(
        self,
        languages: list[str] | None = None,
        since: str = "daily",
        rate_limit_seconds: int = DEFAULT_RATE_LIMIT_SECONDS,
        repos: list[str] | None = None,
        github_token: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.languages = languages or []
        self.since = since
        self.rate_limit_seconds = rate_limit_seconds
        self.repos = repos or []
        self.github_token = github_token
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "builderpulse/2.1.0"},
        )

    def fetch(self, **kwargs: Any) -> list[FeedItem]:
        """Fetch items from all configured sub-features.

        Returns a unified list of ``FeedItem`` with ``sub_source`` in metadata.
        """
        items: list[FeedItem] = []

        # 1. Trending HTML (primary path)
        try:
            items.extend(self._fetch_trending_html())
        except Exception as e:  # pragma: no cover - logged path
            logger.warning(f"GitHub Trending HTML fetch failed: {e}")

        # 2. Search API circuit-breaker (only when Trending returned 0 items)
        if not any(i.metadata.get("sub_source") == SUB_TRENDING for i in items):
            try:
                items.extend(self._fetch_search_api())
            except Exception as e:  # pragma: no cover - logged path
                logger.error(f"GitHub Search API fallback also failed: {e}")

        # 3. Releases (only when repos are configured)
        if self.repos:
            try:
                items.extend(self._fetch_releases())
            except Exception as e:  # pragma: no cover - logged path
                logger.warning(f"GitHub Releases fetch failed: {e}")

        return items

    def _throttle(self) -> None:
        """Sleep enough to respect ``rate_limit_seconds`` between calls."""
        if self.rate_limit_seconds <= 0:
            self._last_request = time.time()
            return
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request = time.time()

    def _fetch_trending_html(self) -> list[FeedItem]:
        """Scrape github.com/trending/{langs}?since=... and return FeedItems.

        Lazy-imports BeautifulSoup so the dependency is only required at runtime
        (the [github] extra installs it; the [dev] extra also includes it for CI).
        """
        from bs4 import BeautifulSoup

        path = ",".join(self.languages) if self.languages else ""
        url = f"https://github.com/trending/{path}?since={self.since}"

        self._throttle()
        resp = self._client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[FeedItem] = []
        for article in soup.select("article.Box-row"):
            a = article.select_one("h2 a")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            if not href.startswith("/"):
                continue
            items.append(
                FeedItem(
                    source_type="github_trending",
                    source_id=f"github_trending:{href}",
                    url=f"https://github.com{href}",
                    title=a.get_text(strip=True),
                    content="",
                    author="",
                    published_at=None,
                    metadata={"sub_source": SUB_TRENDING, "since": self.since},
                )
            )
        return items

    def _fetch_search_api(self) -> list[FeedItem]:
        """GitHub Search API circuit-breaker (when Trending yielded 0 items)."""
        self._throttle()
        url = "https://api.github.com/search/repositories"
        if self.languages:
            q = " OR ".join(f"language:{lang}" for lang in self.languages)
            params: dict[str, str] = {"q": q, "sort": "stars"}
        else:
            params = {"q": "stars:>1", "sort": "stars"}
        resp = self._client.get(url, params=params, headers=self._api_headers())
        resp.raise_for_status()
        items: list[FeedItem] = []
        for item in resp.json().get("items", []):
            html_url = item.get("html_url")
            full_name = item.get("full_name")
            if not html_url or not full_name:
                continue
            items.append(
                FeedItem(
                    source_type="github_trending",
                    source_id=f"github_search:{full_name}",
                    url=html_url,
                    title=full_name,
                    content="",
                    author="",
                    published_at=None,
                    metadata={
                        "sub_source": SUB_SEARCH,
                        "stars": item.get("stargazers_count", 0),
                    },
                )
            )
        return items

    def _fetch_releases(self) -> list[FeedItem]:
        """Fetch latest release for each repo in ``self.repos``."""
        items: list[FeedItem] = []
        for repo in self.repos:
            self._throttle()
            url = f"https://api.github.com/repos/{repo}/releases"
            resp = self._client.get(url, headers=self._api_headers())
            resp.raise_for_status()
            for release in resp.json():
                html_url = release.get("html_url")
                tag = release.get("tag_name", "")
                if not html_url:
                    continue
                items.append(
                    FeedItem(
                        source_type="github_trending",
                        source_id=f"github_release:{repo}:{tag}",
                        url=html_url,
                        title=f"{repo} {tag}",
                        content=release.get("name") or "",
                        author=repo,
                        published_at=release.get("published_at"),
                        metadata={"sub_source": SUB_RELEASES, "repo": repo},
                    )
                )
        return items

    def _api_headers(self) -> dict[str, str]:
        """Headers for the GitHub REST API.

        The ``Authorization`` header is only added when ``github_token`` is set.
        We never log the token value; the global SensitiveDataFilter would
        additionally redact ``token=...`` substrings in any log message.
        """
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            # Use the f-string-REDACTED-friendly form: the global log filter
            # in builderpulse.infra.logger redacts "token=<value>" -> "token=***".
            # We intentionally do NOT log the token itself.
            headers["Authorization"] = f"Bearer {self.github_token}"  # noqa: S105
        return headers

    def health_check(self) -> bool:
        """Cheap health probe — returns True if the source is usable.

        We do NOT call out to GitHub here (cost). Returning True by default lets
        the registry mark this source as available; the actual fetch will
        surface real errors via the per-sub-feature try/except paths.
        """
        return True

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubTrendingSource":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
