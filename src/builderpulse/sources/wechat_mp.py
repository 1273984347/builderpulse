"""WeChat MP (公众号) source — experimental HTML scraper via Sogou proxy.

⚠️ EXPERIMENTAL: WeChat has no public API. Sogou proxy is the
de-facto scraping path because WeChat itself blocks scraping.
Without a proxy, your IP will be banned quickly. Always configure
``sogou_proxy`` and keep ``rate_limit_seconds >= 5``.

The class sets ``__experimental__ = True`` so the PluginRegistry's
auto-disable logic (3 consecutive failures in 1h) can short-circuit
this source instead of letting it hammer a dead endpoint.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from builderpulse.core.models import FeedItem

logger = logging.getLogger(__name__)

# Sub-source tag stored in FeedItem.metadata["sub_source"]
SUB_SOGOU_SCRAPE = "sogou_scrape"

# Conservative default — anti-scraping target. Tests pass 0 to skip.
DEFAULT_RATE_LIMIT_SECONDS = 5


class WeChatMPSource:
    """Fetch articles from WeChat MP accounts (公众号) via Sogou HTML scraping.

    Sogou (weixin.sogou.com) is the de-facto public proxy for WeChat MP
    content because WeChat itself aggressively blocks direct scraping.
    The actual page structure is not part of any stable contract — selectors
    here are best-effort and wrapped in defensive try/except blocks so a
    single page-shape change does not crash the whole pipeline. When parsing
    fails for one MP account, that account is skipped and others continue.
    """

    name = "wechat_mp"
    # Spec §3.10: this MUST be a class attribute, not a module-level one.
    # PluginRegistry (and any ExperimentalPluginProxy) introspect the class.
    __experimental__ = True

    # Sogou search URL — type=2 means "WeChat MP account articles"
    SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        mp_names: list[str] | None = None,
        sogou_proxy: str | None = None,
        rate_limit_seconds: int = DEFAULT_RATE_LIMIT_SECONDS,
        **kwargs: Any,
    ) -> None:
        self.mp_names = mp_names or []
        self.sogou_proxy = sogou_proxy
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request = 0.0
        # httpx uses `proxy` (singular), NOT `proxies` (which is requests)
        self._client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            proxy=sogou_proxy,
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

    # -- public API --------------------------------------------------------

    def fetch(self, **kwargs: Any) -> list[FeedItem]:
        """Fetch articles from all configured MP accounts."""
        if not self.mp_names:
            logger.debug("WeChat MP source: missing or empty mp_names, returning []")
            return []

        items: list[FeedItem] = []
        for mp_name in self.mp_names:
            try:
                items.extend(self._fetch_mp_articles(mp_name))
            except Exception as e:
                # Defensive: one MP's failure must not abort the whole batch.
                # The ExperimentalPluginProxy (or registry) will tally failures
                # for auto-disable.
                logger.warning("WeChat MP fetch failed for %s: %s", mp_name, e)
                continue
        return items

    def health_check(self) -> bool:
        """Cheap health probe — True iff we have at least one MP to follow."""
        return len(self.mp_names) > 0

    # -- internals ---------------------------------------------------------

    def _fetch_mp_articles(self, mp_name: str) -> list[FeedItem]:
        """Scrape Sogou search results for one MP account."""
        self._throttle()
        params = {"type": "2", "query": mp_name}
        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = self._client.get(self.SOGOU_SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        return self._parse_sogou_html(resp.text, mp_name=mp_name)

    def _parse_sogou_html(self, html: str, mp_name: str) -> list[FeedItem]:
        """Parse the Sogou search result page into FeedItem objects.

        Sogou's DOM is not part of any stable contract — it changes
        without notice. We use a defensive parser that:
        - tries the documented selector first (``div.news-box``)
        - falls back to generic list-item selectors
        - silently skips items that lack the minimum required fields
        """
        # Lazy import — bs4 is required by the [sources] extra, but we don't
        # want a hard failure if a user installs builderpulse[base] only.
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        items: list[FeedItem] = []

        # Primary selector chain — try documented shapes first, then
        # fall back to generic list-item shapes when upstream changes.
        boxes = soup.select("div.news-box")
        if not boxes:
            boxes = soup.select("ul.news-list2 li, ul.news-list li")

        for box in boxes:
            try:
                a = box.select_one("h3 a, a")
                if a is None or not a.get("href"):
                    continue

                href = a["href"]
                if href.startswith("/"):
                    full_url = f"https://weixin.sogou.com{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    full_url = f"https://weixin.sogou.com/{href}"

                # Title
                title = a.get_text(strip=True)
                if not title:
                    continue

                # Date — optional; Sogou uses .txt-info or .s-p
                date: str | None = None
                date_el = box.select_one(".txt-info, .s-p")
                if date_el:
                    date = date_el.get_text(strip=True) or None

                # source_id — derive from URL (article_id param if present,
                # otherwise the full URL hash for idempotency)
                source_id = full_url
                if "article_id=" in full_url:
                    source_id = full_url.split("article_id=", 1)[-1].split("&")[0]
                if not source_id:
                    continue

                items.append(
                    FeedItem(
                        source_type="wechat_mp",
                        source_id=source_id,
                        url=full_url,
                        title=title,
                        content="",  # Sogou search result page has no body
                        author=mp_name,  # we only know the account name
                        published_at=date,
                        metadata={"sub_source": SUB_SOGOU_SCRAPE},
                    )
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(
                    "WeChat MP: skipping unparseable article for %s: %s",
                    mp_name,
                    e,
                )
                continue
        return items

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WeChatMPSource":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
