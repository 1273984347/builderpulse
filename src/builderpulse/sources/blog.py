"""Blog content scraper using httpx + BeautifulSoup."""
from __future__ import annotations

import functools
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from builderpulse.core.models import FeedItem

logger = logging.getLogger("builderpulse.sources.blog")


@functools.lru_cache(maxsize=1024)
def _parse_date_utc(date_str: str) -> Optional[datetime]:
    """Parse a date string into a naive UTC datetime.

    Returns None if the string cannot be parsed.
    Aware datetimes are converted to UTC then made naive.
    """
    if not date_str or not date_str.strip():
        return None
    try:
        from dateutil.parser import parse as dateutil_parse
        dt = dateutil_parse(date_str)
    except (ValueError, OverflowError, TypeError):
        return None
    # Convert aware -> UTC naive
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class BlogSource:
    """Scrape blog posts from configured URLs."""

    def __init__(self, urls: list[str] | None = None, strict_date: bool = False):
        self.urls = urls or []
        self.strict_date = strict_date
        self._client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "BuilderPulse/0.9.0"},
        )

    def fetch(self, days: int = 3, limit: int = 10) -> list[FeedItem]:
        """Fetch recent posts from all configured blogs."""
        items: list[FeedItem] = []
        for url in self.urls:
            try:
                items.extend(self._fetch_blog(url, days, limit))
            except Exception as e:
                logger.warning(f"Failed to fetch blog {url}: {e}")
        return items

    def _fetch_blog(self, url: str, days: int, limit: int) -> list[FeedItem]:
        """Fetch and parse a single blog page."""
        from bs4 import BeautifulSoup

        r = self._client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items: list[FeedItem] = []
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Try to extract articles from common blog patterns
        articles = soup.find_all(
            "article"
        ) or soup.find_all("div", class_=re.compile(r"post|article|entry"))

        if not articles:
            # Fallback: extract all links with text
            items.extend(self._extract_links(soup, url, limit))
        else:
            for article in articles:
                item = self._parse_article(article, url)
                if item is None:
                    continue
                # Date filtering
                if item.published_at:
                    dt = _parse_date_utc(item.published_at)
                    if dt is None:
                        if self.strict_date:
                            continue  # skip unparseable dates in strict mode
                    elif dt < cutoff:
                        continue  # too old
                items.append(item)
                if len(items) >= limit:
                    break

        return items[:limit]

    def _parse_article(self, article, base_url: str) -> Optional[FeedItem]:
        """Parse an article element into a FeedItem."""
        # Find title
        title_el = article.find(["h1", "h2", "h3"])
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # Find link
        link_el = article.find("a", href=True)
        link = link_el["href"] if link_el else base_url
        if link.startswith("/"):
            from urllib.parse import urljoin

            link = urljoin(base_url, link)

        # Find content/summary
        content_el = article.find(
            "p"
        ) or article.find("div", class_=re.compile(r"summary|excerpt|desc"))
        content = content_el.get_text(strip=True) if content_el else ""

        # Find published date
        published_at = self._extract_date(article)

        return FeedItem(
            source_type="blog",
            source_id=link,
            url=link,
            title=title,
            content=content,
            author="Unknown",
            published_at=published_at,
        )

    @staticmethod
    def _extract_date(element) -> Optional[str]:
        """Extract a date string from an HTML element."""
        # <time datetime="...">
        time_el = element.find("time")
        if time_el and time_el.get("datetime"):
            return time_el["datetime"]
        # <meta ... content="...">
        meta = element.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"]
        meta = element.find("meta", attrs={"name": "date"})
        if meta and meta.get("content"):
            return meta["content"]
        return None

    def _extract_links(
        self, soup, base_url: str, limit: int
    ) -> list[FeedItem]:
        """Fallback: extract blog-like links."""
        from urllib.parse import urljoin

        items: list[FeedItem] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            if href.startswith("/"):
                href = urljoin(base_url, href)
            if not href.startswith("http"):
                continue
            items.append(
                FeedItem(
                    source_type="blog",
                    source_id=href,
                    url=href,
                    title=text,
                    content="",
                    author="Unknown",
                )
            )
            if len(items) >= limit:
                break
        return items

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
