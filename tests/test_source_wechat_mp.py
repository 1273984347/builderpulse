"""Tests for WeChatMPSource (v2.1.0 Batch 2, Task 21).

Covers:
- HTML parsing of Sogou search result page
- Proxy URL support (anti-scraping bypass)
- Rate limit enforcement between requests
- Empty mp_names → debug log + []
- `__experimental__` is a CLASS attribute (not module-level)
- SourcePlugin protocol compliance
- Defensive parsing (multiple CSS selectors as fallback)
"""

from __future__ import annotations

import logging
import re
import time

import httpx
import pytest
import respx

from builderpulse.sources.wechat_mp import WeChatMPSource


# Realistic (simplified) Sogou search result page HTML
SOGOU_HTML = """
<html><body>
<div class="news-list">
    <div class="news-box">
        <h3>
            <a href="/weixin?type=2&query=TechCrunchChina&article_id=art1">AI News Today</a>
        </h3>
        <p class="txt-info">2026-06-01</p>
    </div>
    <div class="news-box">
        <h3>
            <a href="/weixin?type=2&query=TechCrunchChina&article_id=art2">Tech Update</a>
        </h3>
        <p class="txt-info">2026-06-02</p>
    </div>
    <div class="news-box">
        <h3>
            <a href="https://example.com/abs-link">Absolute Link Article</a>
        </h3>
        <p class="txt-info">2026-06-03</p>
    </div>
</div>
</body></html>
"""


@pytest.fixture
def wechat_source():
    """Source with proxy and throttling disabled for fast tests."""
    return WeChatMPSource(
        mp_names=["TechCrunchChina", "AI_Insight"],
        sogou_proxy=None,
        rate_limit_seconds=0,
    )


def test_fetch_via_sogou_proxy(wechat_source):
    """Mock Sogou search result page, verify article URLs extracted."""
    with respx.mock() as mock:
        mock.get(re.compile(r".*")).mock(
            return_value=httpx.Response(
                200,
                text=SOGOU_HTML,
                headers={"Content-Type": "text/html"},
            )
        )
        items = wechat_source.fetch()

    # We have 2 mp_names; the 3 articles in the page are returned per mp
    # (since we mock the same HTML for both), so 2*3=6 items
    assert len(items) >= 2
    assert all(item.source_type == "wechat_mp" for item in items)
    # sub_source marker on every item
    assert all(item.metadata.get("sub_source") == "sogou_scrape" for item in items)
    # URLs should be absolute (Sogou returns /weixin?type=2&... relative URLs)
    assert all(
        item.url.startswith("https://weixin.sogou.com/weixin")
        or item.url.startswith("https://")
        for item in items
    )
    # Titles extracted
    titles = {item.title for item in items}
    assert "AI News Today" in titles
    assert "Tech Update" in titles


def test_proxy_url_passed_to_requests(monkeypatch):
    """Verify sogou_proxy is passed to the underlying httpx.Client via proxy=.

    We intercept ``httpx.Client`` so we can capture the kwargs the source uses
    — this avoids needing the ``socksio`` extra (required for real SOCKS5
    proxy routing) and keeps the test purely about the wiring.
    """
    captured: dict = {}

    real_client = httpx.Client

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self._real = real_client(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    import builderpulse.sources.wechat_mp as mod

    monkeypatch.setattr(mod.httpx, "Client", FakeClient)

    src = WeChatMPSource(
        mp_names=["abc"],
        sogou_proxy="http://proxy.example.com:1080",
        rate_limit_seconds=0,
    )
    # Touch the source so the linter doesn't complain about an unused var
    assert src.name == "wechat_mp"
    assert captured.get("proxy") == "http://proxy.example.com:1080"


def test_rate_limit_enforced():
    """Verify 2 fetches with rate_limit=1 take ≥0.9 second."""
    src = WeChatMPSource(
        mp_names=["a"],
        sogou_proxy=None,
        rate_limit_seconds=1,
    )
    with respx.mock() as mock:
        mock.get(re.compile(r".*")).mock(
            return_value=httpx.Response(200, text="<html></html>")
        )
        start = time.time()
        src.fetch()
        src.fetch()  # second call should wait for rate limit
        elapsed = time.time() - start
    # Should take at least ~1 second (rate limit) — use 0.9s to avoid CI flake
    assert elapsed >= 0.9, f"Expected ≥0.9s rate limit, got {elapsed:.2f}s"


def test_missing_mp_names_logs_debug_and_returns_empty(caplog):
    """Empty mp_names → DEBUG log + return []."""
    src = WeChatMPSource(mp_names=[], sogou_proxy=None, rate_limit_seconds=0)
    caplog.set_level(logging.DEBUG, logger="builderpulse.sources.wechat_mp")
    items = src.fetch()
    assert items == []
    # Verify a DEBUG log mentions mp_names being empty/missing
    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and "mp_names" in r.getMessage().lower()
        and ("missing" in r.getMessage().lower() or "empty" in r.getMessage().lower())
    ]
    assert matching, (
        "Expected a DEBUG log mentioning empty/missing mp_names; "
        f"got: {[r.getMessage() for r in caplog.records]}"
    )


def test_experimental_class_attribute():
    """`__experimental__` is on the CLASS, not the module (per spec §3.10)."""
    import builderpulse.sources.wechat_mp as mod
    from builderpulse.sources.wechat_mp import WeChatMPSource

    # Class-level attribute check
    assert hasattr(WeChatMPSource, "__experimental__")
    assert WeChatMPSource.__experimental__ is True
    # Module-level must NOT have it set to True (sanity check — a class
    # attribute should not leak to module globals)
    assert not getattr(mod, "__experimental__", False)


def test_health_check_returns_true_with_mps():
    """health_check returns True when mp_names is non-empty."""
    src = WeChatMPSource(mp_names=["abc"], sogou_proxy=None, rate_limit_seconds=0)
    assert src.health_check() is True


def test_health_check_returns_false_with_no_mps():
    """health_check returns False when mp_names is empty (per spec)."""
    src = WeChatMPSource(mp_names=[], sogou_proxy=None, rate_limit_seconds=0)
    assert src.health_check() is False


def test_defensive_fallback_selectors():
    """When primary selectors miss, fall back to li / h3 a selectors.

    Sogou sometimes returns a slightly different DOM (e.g. ul.news-list2 li).
    The source must parse any of these variants.
    """
    fallback_html = """
    <html><body>
    <ul class="news-list2">
        <li>
            <h3><a href="/weixin?type=2&query=abc&article_id=fallback1">Found via fallback</a></h3>
        </li>
    </ul>
    </body></html>
    """
    src = WeChatMPSource(
        mp_names=["u1"],
        sogou_proxy=None,
        rate_limit_seconds=0,
    )
    with respx.mock() as mock:
        mock.get(re.compile(r".*")).mock(
            return_value=httpx.Response(200, text=fallback_html)
        )
        items = src.fetch()
    assert len(items) >= 1
    assert any("fallback" in i.title.lower() for i in items)
