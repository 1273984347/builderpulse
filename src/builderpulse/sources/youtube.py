"""YouTube content source via RSS feeds."""

from __future__ import annotations

import logging

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger("builderpulse.sources.youtube")


class YouTubeSource:
    """Fetch videos from YouTube channels via RSS."""

    def __init__(self, channels: list[dict] | None = None):
        self.channels = channels or []  # [{"id": "UCxxx", "name": "Channel"}]
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def fetch(self, limit: int = 10) -> list[FeedItem]:
        items = []
        for ch in self.channels:
            import feedparser

            ch_id = ch.get("id")
            ch_name = ch.get("name", ch_id)
            try:
                url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}"
                r = self._client.get(url)
                r.raise_for_status()
                feed = feedparser.parse(r.text)
                for entry in feed.entries[:limit]:
                    items.append(
                        FeedItem(
                            source_type="youtube_video",
                            source_id=entry.get("yt_videoid", entry.id),
                            url=entry.link,
                            title=entry.title,
                            content=entry.get("summary", ""),
                            author=ch_name,
                            published_at=entry.get("published"),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch YouTube channel {ch_name}: {e}")
        return items

    def close(self):
        self._client.close()
