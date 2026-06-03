"""Podcast RSS feed source."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger("builderpulse.sources.podcast")


class PodcastSource:
    """Fetch podcast episodes from RSS feeds."""

    def __init__(self, feeds: list[str] | None = None):
        self.feeds = feeds or []
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def fetch(self, days: int = 7, limit: int = 20) -> list[FeedItem]:
        """Fetch recent episodes from all configured feeds."""
        items: list[FeedItem] = []
        for feed_url in self.feeds:
            try:
                items.extend(self._fetch_feed(feed_url, days, limit))
            except Exception as e:
                logger.warning(f"Failed to fetch podcast {feed_url}: {e}")
        return items

    def _fetch_feed(self, feed_url: str, days: int, limit: int) -> list[FeedItem]:
        """Fetch and parse a single RSS feed."""
        import feedparser

        r = self._client.get(feed_url)
        r.raise_for_status()
        feed = feedparser.parse(r.text)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        items: list[FeedItem] = []

        for entry in feed.entries[:limit]:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(
                    *entry.published_parsed[:6], tzinfo=timezone.utc
                ).isoformat()

            # Skip old entries
            if published:
                pub_dt = datetime.fromisoformat(published)
                if pub_dt < cutoff:
                    continue

            # Get content (prefer content, fallback to summary)
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary

            # Use GUID as stable ID, fallback to link
            guid = getattr(entry, "id", None) or entry.link

            items.append(
                FeedItem(
                    source_type="podcast",
                    source_id=guid,
                    url=entry.link,
                    title=entry.title,
                    content=content,
                    author=getattr(
                        entry, "author", feed.feed.get("title", "Unknown")
                    ),
                    published_at=published,
                    metadata={
                        "feed_url": feed_url,
                        "feed_title": feed.feed.get("title", ""),
                    },
                )
            )

        return items

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
