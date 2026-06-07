"""Xiaohongshu (小红书) source — experimental HTML scraper.

⚠️ EXPERIMENTAL: Xiaohongshu has no public API and uses aggressive
anti-scraping. Without a SOCKS5/HTTP proxy, your IP will be banned within
minutes. Always configure ``proxy_url`` and keep ``rate_limit_seconds >= 5``.

The class sets ``__experimental__ = True`` so the PluginRegistry's
auto-disable logic (3 consecutive failures in 1h) can short-circuit this
source instead of letting it hammer a dead endpoint.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger(__name__)

# Sub-source tag stored in FeedItem.metadata["sub_source"]
SUB_PROFILE_SCRAPE = "profile_scrape"

# Conservative default — anti-scraping target. Tests pass 0 to skip.
DEFAULT_RATE_LIMIT_SECONDS = 5


class XiaohongshuSource:
    """Fetch notes (笔记) from Xiaohongshu user profiles via HTML scraping.

    The actual page structure is not part of any stable contract — selectors
    here are best-effort and wrapped in defensive try/except blocks so a
    single page-shape change does not crash the whole pipeline. When parsing
    fails for a user, that user is skipped and other users continue.
    """

    name = "xiaohongshu"
    # Spec §3.10: this MUST be a class attribute, not a module-level one.
    # PluginRegistry (and any ExperimentalPluginProxy) introspect the class.
    __experimental__ = True

    PROFILE_URL_TEMPLATE = "https://www.xiaohongshu.com/user/profile/{user_id}"

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        user_ids: list[str] | None = None,
        proxy_url: str | None = None,
        rate_limit_seconds: int = DEFAULT_RATE_LIMIT_SECONDS,
        user_agents: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.user_ids = user_ids or []
        self.proxy_url = proxy_url
        self.rate_limit_seconds = rate_limit_seconds
        self.user_agents = user_agents or [self.DEFAULT_USER_AGENT]
        self._ua_index = 0
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            proxy=proxy_url,  # httpx uses `proxy` (singular), not `proxies`
        )

    # -- throttling --------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep enough to respect ``rate_limit_seconds`` between calls."""
        if self.rate_limit_seconds <= 0:
            self._last_request = time.time()
            return
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request = time.time()

    def _next_ua(self) -> str:
        """Round-robin through ``user_agents`` for UA rotation."""
        ua = self.user_agents[self._ua_index % len(self.user_agents)]
        self._ua_index += 1
        return ua

    # -- public API --------------------------------------------------------

    def fetch(self, **kwargs: Any) -> list[FeedItem]:
        """Fetch notes from all configured user profiles."""
        if not self.user_ids:
            logger.debug("Xiaohongshu source: missing or empty user_ids, returning []")
            return []

        items: list[FeedItem] = []
        for user_id in self.user_ids:
            try:
                items.extend(self._fetch_user_profile(user_id))
            except Exception as e:
                # Defensive: one user's failure must not abort the whole batch.
                # The ExperimentalPluginProxy (or registry) will tally failures
                # for auto-disable.
                logger.warning("Xiaohongshu fetch failed for user %s: %s", user_id, e)
                continue
        return items

    def health_check(self) -> bool:
        """Cheap health probe — True iff we have at least one user to follow."""
        return len(self.user_ids) > 0

    # -- internals ---------------------------------------------------------

    def _fetch_user_profile(self, user_id: str) -> list[FeedItem]:
        """Scrape one user's profile page for their notes (笔记)."""
        self._throttle()
        url = self.PROFILE_URL_TEMPLATE.format(user_id=user_id)
        headers = {
            "User-Agent": self._next_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = self._client.get(url, headers=headers)
        resp.raise_for_status()
        return self._parse_profile_html(resp.text, user_id=user_id)

    def _parse_profile_html(self, html: str, user_id: str) -> list[FeedItem]:
        """Parse the profile page HTML into FeedItem objects.

        The real Xiaohongshu DOM is heavily obfuscated and changes without
        notice. We use a defensive parser that:
        - tries the documented selector first (``section.note-item``)
        - falls back to a generic ``a[href*='/explore/']`` scan
        - silently skips notes that lack the minimum required fields
        """
        # Lazy import — bs4 is required by the [github] extra, but we don't
        # want a hard failure if a user installs builderpulse[base] only.
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        items: list[FeedItem] = []

        # Primary selector — the documented one
        notes = soup.select("section.note-item")
        if not notes:
            # Fallback selector — find any link that looks like a note URL
            notes = soup.select("a[href*='/explore/']")

        for note in notes:
            try:
                a = note if note.name == "a" else note.select_one("a.cover")
                if a is None:
                    a = note
                href = a.get("href") if hasattr(a, "get") else None
                if not href:
                    continue

                if href.startswith("/"):
                    full_url = f"https://www.xiaohongshu.com{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    full_url = f"https://www.xiaohongshu.com/{href}"

                # Title — try .title first, then the link's text/title attr
                title = ""
                title_el = (
                    note.select_one(".title") if hasattr(note, "select_one") else None
                )
                if title_el:
                    title = title_el.get_text(strip=True)
                elif hasattr(a, "get_text"):
                    title = a.get_text(strip=True)
                elif hasattr(a, "get"):
                    title = a.get("title", "") or ""

                # Date — optional; we use a `.date` element or `time[datetime]`
                date: str | None = None
                if hasattr(note, "select_one"):
                    date_el = note.select_one(".date") or note.select_one(
                        "time[datetime]"
                    )
                    if date_el:
                        date = date_el.get("datetime") or date_el.get_text(strip=True)

                # source_id — derive from the note slug (last URL path segment)
                # e.g. /explore/abc123?xsec_token=xyz  →  "abc123"
                source_id = (
                    full_url.split("/explore/", 1)[-1].split("?")[0].split("/")[0]
                )
                if not source_id:
                    continue

                items.append(
                    FeedItem(
                        source_type="xiaohongshu",
                        source_id=source_id,
                        url=full_url,
                        title=title,
                        content="",  # profile pages don't include full body
                        author=user_id,  # we don't know the display name without login
                        published_at=date,
                        metadata={"sub_source": SUB_PROFILE_SCRAPE},
                    )
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(
                    "Xiaohongshu: skipping unparseable note for user %s: %s",
                    user_id,
                    e,
                )
                continue
        return items

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "XiaohongshuSource":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
