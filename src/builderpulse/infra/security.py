"""URL safety checks and filename sanitization."""

from __future__ import annotations
import re
from urllib.parse import urlparse

TRUSTED_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "douyin.com",
    "x.com",
    "twitter.com",
    "github.com",
}


def is_safe_url(url: str) -> bool:
    """Check if URL is from a trusted domain."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.netloc.lower().lstrip("www.")
        return any(host == d or host.endswith(f".{d}") for d in TRUSTED_DOMAINS)
    except Exception:
        return False


def sanitize_filename(name: str, max_len: int = 200) -> str:
    """Sanitize a string for use as a filename."""
    # Remove/replace invalid chars
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Remove control chars
    name = re.sub(r"[\x00-\x1f]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Truncate
    if len(name) > max_len:
        name = name[:max_len]
    return name or "untitled"
