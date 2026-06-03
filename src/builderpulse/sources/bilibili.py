"""Bilibili content source — fetch user's video list."""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
from typing import Optional

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger("builderpulse.sources.bilibili")

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


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
        nav = self._client.get("https://api.bilibili.com/x/web-interface/nav").json()
        wbi = nav.get("data", {}).get("wbi_img", {})
        img_key = wbi.get("img_url", "").split("/")[-1].split(".")[0]
        sub_key = wbi.get("sub_url", "").split("/")[-1].split(".")[0]
        mixin_key = "".join((img_key + sub_key)[i] for i in _MIXIN_KEY_ENC_TAB)[:32]
        params["wts"] = int(time.time())
        params = {
            k: "".join(c for c in str(v) if c not in "!'()*")
            for k, v in sorted(params.items())
        }
        query = urllib.parse.urlencode(params)
        params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
        return params

    def close(self):
        self._client.close()
