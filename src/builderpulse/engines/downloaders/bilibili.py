"""Bilibili video downloader with WBI signing."""
from __future__ import annotations

import hashlib
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

from builderpulse.core.models import SourceRef, DownloadResult
from .base import Downloader

# WBI mixin key encoding table (from Bilibili web)
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


class BilibiliDownloader(Downloader):
    """Download videos from Bilibili using their API with WBI signing."""

    def __init__(self, sessdata: str | None = None):
        self.sessdata = sessdata
        self._client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=30,
        )

    def can_handle(self, source: SourceRef) -> bool:
        return source.source_type == "bilibili"

    @property
    def name(self) -> str:
        return "bilibili"

    def download(self, source: SourceRef, output_dir: Path) -> DownloadResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        bvid = source.native_id

        # Get video info with WBI signing
        info = self._get_video_info(bvid)
        title = info.get("title", "Unknown")

        # Get video stream URL
        cid = info.get("cid") or self._get_cid(bvid, info.get("aid"))
        stream_url = self._get_stream_url(bvid, cid)

        # Download
        output_path = output_dir / f"{bvid}.mp4"
        self._download_file(stream_url, output_path)

        duration = info.get("duration", 0)
        return DownloadResult(
            path=str(output_path),
            source_type="bilibili",
            native_id=bvid,
            title=title,
            duration=float(duration),
        )

    def _get_video_info(self, bvid: str) -> dict:
        """Get video info with WBI signing."""
        params = {"bvid": bvid}
        signed = self._wbi_sign(params)
        url = "https://api.bilibili.com/x/web-interface/view"
        r = self._client.get(url, params=signed)
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API error: {data.get('message')}")
        return data["data"]

    def _get_cid(self, bvid: str, aid: int | None) -> int:
        """Get first page cid."""
        if aid:
            url = f"https://api.bilibili.com/x/player/pagelist?aid={aid}"
        else:
            url = f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}"
        r = self._client.get(url)
        pages = r.json().get("data", [])
        if not pages:
            raise RuntimeError("No pages found")
        return pages[0]["cid"]

    def _get_stream_url(self, bvid: str, cid: int) -> str:
        """Get video stream URL."""
        params = {"bvid": bvid, "cid": cid, "qn": 64, "fnval": 16}
        signed = self._wbi_sign(params)
        url = "https://api.bilibili.com/x/player/wbi/playurl"

        headers: dict[str, str] = {}
        if self.sessdata:
            headers["Cookie"] = f"SESSDATA={self.sessdata}"

        r = self._client.get(url, params=signed, headers=headers)
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Stream URL error: {data.get('message')}")

        dash = data["data"].get("dash")
        if dash:
            # Pick first video stream
            video_url = dash["video"][0]["baseUrl"]
            return video_url

        # Fallback to durl
        return data["data"]["durl"][0]["url"]

    def _wbi_sign(self, params: dict) -> dict:
        """WBI signing: fetch keys, compute mixin_key, sign params."""
        # Get img_key and sub_key from nav API
        nav = self._client.get(
            "https://api.bilibili.com/x/web-interface/nav"
        ).json()
        wbi_img = nav.get("data", {}).get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        img_key = img_url.split("/")[-1].split(".")[0] if img_url else ""
        sub_key = sub_url.split("/")[-1].split(".")[0] if sub_url else ""

        mixin_key = self._get_mixin_key(img_key + sub_key)

        params["wts"] = int(time.time())
        # Sort and filter forbidden characters
        params = {
            k: "".join(c for c in str(v) if c not in "!'()*")
            for k, v in sorted(params.items())
        }
        query = urllib.parse.urlencode(params)
        params["w_rid"] = hashlib.md5(
            (query + mixin_key).encode()
        ).hexdigest()
        return params

    @staticmethod
    def _get_mixin_key(raw: str) -> str:
        """Compute mixin key from raw key using enc tab."""
        return "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB)[:32]

    def _download_file(self, url: str, output_path: Path) -> None:
        """Download file from URL with proper referer header."""
        headers = {"Referer": "https://www.bilibili.com"}
        with self._client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
