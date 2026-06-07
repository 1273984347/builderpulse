"""Tests for XiaohongshuSource (v2.1.0 Batch 2, Task 20).

Covers:
- HTML parsing of Xiaohongshu user profile page
- Proxy URL support (anti-scraping bypass)
- Rate limit enforcement between requests
- Empty user_ids → debug log + []
- `__experimental__` is a CLASS attribute (not module-level)
- SourcePlugin protocol compliance
- Defensive parsing (fallback selector) when page structure changes
"""

from __future__ import annotations

import logging
import time

import httpx
import pytest
import respx

from builderpulse.sources.xiaohongshu import XiaohongshuSource


# Realistic (simplified) Xiaohongshu profile HTML — the real selectors
# are unstable, so the source must be defensive.
PROFILE_HTML = """
<html><body>
<section class="note-item" data-v-a1b2c3>
    <a class="cover" href="/explore/abc123?xsec_token=xyz">
        <img src="https://ci.xiaohongshu.com/abc.jpg" />
    </a>
    <div class="title">Beautiful sunset today</div>
    <div class="date">2026-06-01</div>
</section>
<section class="note-item" data-v-a1b2c3>
    <a class="cover" href="/explore/def456?xsec_token=xyz">
        <img src="https://ci.xiaohongshu.com/def.jpg" />
    </a>
    <div class="title">My new recipe</div>
    <div class="date">2026-06-02</div>
</section>
</body></html>
"""


@pytest.fixture
def xhs_source():
    """Source with proxy and throttling disabled for fast tests."""
    return XiaohongshuSource(
        user_ids=["abc123", "def456"],
        proxy_url=None,
        rate_limit_seconds=0,
    )


def test_fetch_parses_user_profile(xhs_source):
    """Mock Xiaohongshu profile HTML, verify items extracted."""
    with respx.mock() as mock:
        mock.get("https://www.xiaohongshu.com/user/profile/abc123").mock(
            return_value=httpx.Response(
                200,
                text=PROFILE_HTML,
                headers={"Content-Type": "text/html"},
            )
        )
        mock.get("https://www.xiaohongshu.com/user/profile/def456").mock(
            return_value=httpx.Response(
                200,
                text=PROFILE_HTML,
                headers={"Content-Type": "text/html"},
            )
        )
        items = xhs_source.fetch()

    # 2 users × 2 notes each
    assert len(items) == 4
    assert all(item.source_type == "xiaohongshu" for item in items)
    assert all(item.metadata.get("sub_source") == "profile_scrape" for item in items)
    assert any("sunset" in item.title for item in items)
    assert any("recipe" in item.title for item in items)
    # URLs should be absolute
    assert all(
        item.url.startswith("https://www.xiaohongshu.com/explore/") for item in items
    )


def test_defensive_fallback_selector_parses_explore_links():
    """When section.note-item is missing, fall back to /explore/ link scan."""
    fallback_html = """
    <html><body>
    <a href="/explore/xyz789?xsec_token=q">Found via fallback</a>
    <a href="/explore/wvu000?xsec_token=q">Another note</a>
    </body></html>
    """
    src = XiaohongshuSource(
        user_ids=["u1"],
        proxy_url=None,
        rate_limit_seconds=0,
    )
    with respx.mock() as mock:
        mock.get("https://www.xiaohongshu.com/user/profile/u1").mock(
            return_value=httpx.Response(200, text=fallback_html)
        )
        items = src.fetch()
    assert len(items) == 2
    assert {i.source_id for i in items} == {"xyz789", "wvu000"}


def test_proxy_url_passed_to_client(monkeypatch):
    """Verify proxy_url is passed to the underlying httpx.Client via proxy=.

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
    # Also patch the import location used by the source module
    import builderpulse.sources.xiaohongshu as mod

    monkeypatch.setattr(mod.httpx, "Client", FakeClient)

    src = XiaohongshuSource(
        user_ids=["abc"],
        proxy_url="http://proxy.example.com:1080",
        rate_limit_seconds=0,
    )
    # Touch the source so the linter doesn't complain about an unused var
    assert src.name == "xiaohongshu"
    assert captured.get("proxy") == "http://proxy.example.com:1080"


def test_proxy_url_none_means_no_proxy(monkeypatch):
    """When proxy_url is None, the underlying Client receives proxy=None."""
    captured: dict = {}

    real_client = httpx.Client

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self._real = real_client(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    import builderpulse.sources.xiaohongshu as mod

    monkeypatch.setattr(mod.httpx, "Client", FakeClient)

    XiaohongshuSource(
        user_ids=["abc"],
        proxy_url=None,
        rate_limit_seconds=0,
    )
    # When proxy_url is None, the source passes proxy=None to httpx.Client
    assert captured.get("proxy") is None


def test_rate_limit_enforced():
    """Verify 2 fetches with rate_limit=1 take ≥0.9 second."""
    src = XiaohongshuSource(
        user_ids=["a"],
        proxy_url=None,
        rate_limit_seconds=1,
    )
    with respx.mock() as mock:
        mock.get("https://www.xiaohongshu.com/user/profile/a").mock(
            return_value=httpx.Response(200, text="<html></html>")
        )
        start = time.time()
        src.fetch()
        src.fetch()  # second call should wait for rate limit
        elapsed = time.time() - start
    # Should take at least ~1 second (rate limit) — use 0.9s to avoid CI flake
    assert elapsed >= 0.9, f"Expected ≥0.9s rate limit, got {elapsed:.2f}s"


def test_missing_user_ids_logs_debug_and_returns_empty(caplog):
    """Empty user_ids → DEBUG log + return []."""
    src = XiaohongshuSource(user_ids=[], proxy_url=None, rate_limit_seconds=0)
    caplog.set_level(logging.DEBUG, logger="builderpulse.sources.xiaohongshu")
    items = src.fetch()
    assert items == []
    # Verify a DEBUG log mentions user_ids being empty/missing
    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and "user_ids" in r.getMessage().lower()
        and ("missing" in r.getMessage().lower() or "empty" in r.getMessage().lower())
    ]
    assert matching, (
        "Expected a DEBUG log mentioning empty/missing user_ids; "
        f"got: {[r.getMessage() for r in caplog.records]}"
    )


def test_experimental_class_attribute():
    """`__experimental__` is on the CLASS, not the module (per spec §3.10)."""
    import builderpulse.sources.xiaohongshu as mod
    from builderpulse.sources.xiaohongshu import XiaohongshuSource

    # Class-level attribute check
    assert hasattr(XiaohongshuSource, "__experimental__")
    assert XiaohongshuSource.__experimental__ is True
    # Module-level must NOT have it set to True (sanity check — a class
    # attribute should not leak to module globals)
    assert not getattr(mod, "__experimental__", False)


def test_health_check_returns_true_with_users():
    """health_check returns True when user_ids is non-empty."""
    src = XiaohongshuSource(user_ids=["abc"], proxy_url=None, rate_limit_seconds=0)
    assert src.health_check() is True


def test_health_check_returns_false_with_no_users():
    """health_check returns False when user_ids is empty (per spec)."""
    src = XiaohongshuSource(user_ids=[], proxy_url=None, rate_limit_seconds=0)
    assert src.health_check() is False
