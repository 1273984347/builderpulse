"""Douyin video downloader using Playwright to intercept media URLs."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from builderpulse.core.models import SourceRef, DownloadResult
from .base import Downloader


class DouyinDownloader(Downloader):
    """Download Douyin videos by intercepting media URLs via Playwright."""

    def can_handle(self, source: SourceRef) -> bool:
        return source.source_type == "douyin"

    @property
    def name(self) -> str:
        return "douyin"

    def download(self, source: SourceRef, output_dir: Path) -> DownloadResult:
        """Download Douyin video using Playwright."""
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright not installed. Run: "
                "pip install builderpulse[browser] && python -m playwright install"
            )

        media_urls: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()

                # Intercept network requests to capture media URLs
                def handle_response(response) -> None:
                    url = response.url
                    # Parse the URL to get exact netloc — avoids
                    # 'douyinvod.com.evil.com/path.mp4' bypass of substring check.
                    parsed = urlparse(url)
                    netloc = parsed.netloc
                    if (netloc == "douyinvod.com" or netloc.endswith(".douyinvod.com")) \
                            and (url.lower().endswith(".mp4") or url.lower().endswith(".m4a")):
                        media_urls.append(url)

                page.on("response", handle_response)
                page.goto(source.url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)  # Wait for media to load

                title = page.title() or "Douyin Video"
            finally:
                browser.close()  # P1 fix: always close browser on exception

        if not media_urls:
            raise RuntimeError("Could not capture Douyin media URL")

        # Download the first media URL
        import httpx

        media_url = media_urls[0]
        output_path = output_dir / f"{source.native_id.replace('/', '_')}.mp4"

        with httpx.stream("GET", media_url, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return DownloadResult(
            path=str(output_path),
            source_type="douyin",
            native_id=source.native_id,
            title=title,
            duration=None,  # Duration not easily available
        )
