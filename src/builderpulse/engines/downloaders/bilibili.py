"""Bilibili video downloader with WBI signing."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from builderpulse.core.models import SourceRef, DownloadResult
from builderpulse.core.shared_utils import wbi_sign
from .base import Downloader


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

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

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
            # P1 fix: validate SESSDATA doesn't contain injection chars
            if ';' in self.sessdata or '\n' in self.sessdata or '\r' in self.sessdata:
                raise ValueError("SESSDATA contains invalid characters")
            headers["Cookie"] = f"SESSDATA={self.sessdata}"

        r = self._client.get(url, params=signed, headers=headers)
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Stream URL error: {data.get('message')}")

        dash = data["data"].get("dash")
        if dash and dash.get("video"):
            return dash["video"][0]["baseUrl"]

        # Fallback to durl
        durl_list = data["data"].get("durl", [])
        if durl_list:
            return durl_list[0]["url"]
        raise RuntimeError("No stream URL found")

    def _wbi_sign(self, params: dict) -> dict:
        """WBI signing: fetch keys, compute mixin_key, sign params."""
        return wbi_sign(params, self._client)

    def _download_file(self, url: str, output_path: Path) -> None:
        """Download file from URL with proper referer header."""
        headers = {"Referer": "https://www.bilibili.com"}
        with self._client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
