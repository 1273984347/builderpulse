"""Bilibili content source — fetch user's video list."""

from __future__ import annotations

import logging

import httpx

from builderpulse.core.models import FeedItem
from builderpulse.core.shared_utils import wbi_sign

logger = logging.getLogger("builderpulse.sources.bilibili")


class BilibiliSource:
    """Fetch videos from Bilibili users."""

    def __init__(self, users: list[dict] | None = None, sessdata: str | None = None):
        self.users = users or []  # [{"mid": 123, "name": "UP主"}]
        self.sessdata = sessdata
        self._client = httpx.Client(
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"},
        )

    def fetch(self, limit: int = 5) -> list[FeedItem]:
        items = []
        for user in self.users:
            mid = user.get("mid")
            name = user.get("name", str(mid))
            try:
                items.extend(self._fetch_user_videos(mid, name, limit))
            except Exception as e:
                logger.warning(f"Failed to fetch Bilibili user {name}: {e}")
        return items

    def _fetch_user_videos(self, mid: int, name: str, limit: int) -> list[FeedItem]:
        params = {"mid": mid, "ps": limit, "pn": 1, "order": "pubdate"}
        signed = self._wbi_sign(params)
        url = "https://api.bilibili.com/x/space/wbi/arc/search"
        r = self._client.get(url, params=signed)
        r.raise_for_status()  # P1 fix: check HTTP status before parsing
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API error: {data.get('message')}")

        items = []
        for v in data.get("data", {}).get("list", {}).get("vlist", []):
            items.append(
                FeedItem(
                    source_type="bilibili_video",
                    source_id=v.get("bvid", str(v.get("aid"))),
                    url=f"https://www.bilibili.com/video/{v.get('bvid')}",
                    title=v.get("title", ""),
                    content=v.get("description", ""),
                    author=name,
                    published_at=str(v.get("created")),
                )
            )
        return items

    def _wbi_sign(self, params: dict) -> dict:
        """Sign params using shared WBI utility."""
        return wbi_sign(params, self._client)

    def close(self):
        self._client.close()
