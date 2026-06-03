"""X/Twitter source with API + Nitter RSS fallback."""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger("builderpulse.sources.twitter")

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.cz",
    "https://nitter.privacydev.net",
]


class TwitterSource:
    """Fetch tweets via X API or Nitter RSS fallback."""

    def __init__(
        self,
        bearer_token: str | None = None,
        accounts: list[str] | None = None,
    ):
        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN")
        self.accounts = accounts or []
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def fetch(self, limit: int = 10) -> list[FeedItem]:
        """Fetch tweets from all configured accounts."""
        if not self.accounts:
            return []

        if self.bearer_token:
            try:
                return self._fetch_api(limit)
            except Exception as e:
                logger.warning(f"X API failed: {e}, falling back to Nitter")

        return self._fetch_nitter(limit)

    def _fetch_api(self, limit: int) -> list[FeedItem]:
        """Fetch via X API v2."""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        items: list[FeedItem] = []

        for account in self.accounts:
            try:
                # Get user ID
                user_url = f"https://api.twitter.com/2/users/by/username/{account}"
                r = self._client.get(user_url, headers=headers)
                r.raise_for_status()
                user_data = r.json().get("data", {})
                user_id = user_data.get("id")

                if not user_id:
                    continue

                # Get tweets
                tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
                params = {
                    "max_results": min(limit, 100),
                    "exclude": "retweets,replies",
                }
                r = self._client.get(tweets_url, headers=headers, params=params)
                r.raise_for_status()

                for tweet in r.json().get("data", []):
                    items.append(
                        FeedItem(
                            source_type="tweet",
                            source_id=tweet["id"],
                            url=f"https://x.com/{account}/status/{tweet['id']}",
                            title=tweet["text"][:100],
                            content=tweet["text"],
                            author=account,
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch tweets for {account}: {e}")

        return items

    def _fetch_nitter(self, limit: int) -> list[FeedItem]:
        """Fetch via Nitter RSS (no API key needed)."""
        import feedparser

        items: list[FeedItem] = []
        for account in self.accounts:
            for instance in NITTER_INSTANCES:
                try:
                    rss_url = f"{instance}/{account}/rss"
                    r = self._client.get(rss_url)
                    if r.status_code != 200:
                        continue

                    feed = feedparser.parse(r.text)
                    for entry in feed.entries[:limit]:
                        items.append(
                            FeedItem(
                                source_type="tweet",
                                source_id=entry.get("id", entry.link),
                                url=entry.link,
                                title=entry.title[:100] if entry.title else "",
                                content=entry.get("summary", entry.title or ""),
                                author=account,
                            )
                        )
                    break  # Success, move to next account
                except Exception:
                    continue

        return items

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
