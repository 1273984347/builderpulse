"""
BuilderPulse data models — lightweight dataclasses for the processing pipeline.

SourceRef → DownloadResult → TranscriptResult → FeedItem
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .state import make_idem_key, make_idem_key_from_url


# ── URL patterns ──────────────────────────────────────────────────────

_YT_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
_BILI_RE = re.compile(r"BV[a-zA-Z0-9]+")
_TWEET_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class SourceRef:
    """Reference to a content source (video, tweet, local file, etc.)."""

    source_type: str
    native_id: str
    url: str
    title: Optional[str] = None

    @classmethod
    def from_url(cls, url: str, title: Optional[str] = None) -> SourceRef:
        """Auto-detect source type from URL and extract native ID."""
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path

        # YouTube
        if host in _YT_HOSTS:
            if host == "youtu.be":
                video_id = path.lstrip("/")
            else:
                qs = parse_qs(parsed.query)
                video_id = qs.get("v", [""])[0]
            return cls(
                source_type="youtube",
                native_id=video_id,
                url=url,
                title=title,
            )

        # Bilibili
        if "bilibili.com" in host:
            m = _BILI_RE.search(url)
            native_id = m.group(0) if m else make_idem_key_from_url(url)
            return cls(
                source_type="bilibili",
                native_id=native_id,
                url=url,
                title=title,
            )

        # Douyin
        if "douyin.com" in host:
            return cls(
                source_type="douyin",
                native_id=make_idem_key_from_url(url),
                url=url,
                title=title,
            )

        # Twitter / X
        if host in _TWEET_HOSTS:
            # URL pattern: /user/status/1234567890
            parts = path.strip("/").split("/")
            tweet_id = parts[-1] if len(parts) >= 3 and parts[-2] == "status" else ""
            if not tweet_id:
                raise ValueError(f"Cannot extract tweet ID from URL: {url}")
            return cls(
                source_type="twitter",
                native_id=tweet_id,
                url=url,
                title=title,
            )

        # Local file
        if url.startswith("/"):
            return cls(
                source_type="local",
                native_id=url,
                url=url,
                title=title,
            )

        # Generic web
        return cls(
            source_type="web",
            native_id=make_idem_key_from_url(url),
            url=url,
            title=title,
        )

    @property
    def idem_key(self) -> str:
        return make_idem_key(self.source_type, self.native_id)


@dataclass
class DownloadResult:
    """Result of downloading a source."""

    path: str
    source_type: str
    native_id: str
    title: Optional[str] = None
    duration: Optional[float] = None


@dataclass
class TranscriptResult:
    """Result of transcribing audio/video."""

    text: str
    language: str
    engine: str
    segments: list[dict] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class FeedItem:
    """Aggregated content item ready for delivery."""

    source_type: str
    source_id: str
    url: str
    title: str
    content: str
    author: str
    published_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def idem_key(self) -> str:
        return make_idem_key(self.source_type, self.source_id)
