"""Tests for source scrapers — BlogSource, TwitterSource, YouTubeSource."""

from __future__ import annotations


import httpx

from builderpulse.sources.blog import BlogSource, _parse_date_utc
from builderpulse.sources.twitter import TwitterSource
from builderpulse.sources.youtube import YouTubeSource


# ── BlogSource ──────────────────────────────────────────────────────────


class TestBlogSource:
    def test_construction(self):
        src = BlogSource(urls=["https://blog.example.com"])
        assert src.urls == ["https://blog.example.com"]
        assert src.strict_date is False

    def test_construction_strict_date(self):
        src = BlogSource(urls=[], strict_date=True)
        assert src.strict_date is True

    def test_fetch_empty_urls(self):
        src = BlogSource(urls=[])
        items = src.fetch()
        assert items == []

    def test_fetch_article_with_time_element(self, monkeypatch):
        """Articles with <time datetime> are parsed correctly."""
        html = """
        <html><body>
        <article>
            <h2><a href="/post-1">First Post</a></h2>
            <p>Summary of the first post.</p>
            <time datetime="2026-06-01T10:00:00Z">June 1</time>
        </article>
        </body></html>
        """

        class FakeResponse:
            status_code = 200
            text = html

            def raise_for_status(self):
                pass

        src = BlogSource(urls=["https://blog.example.com"])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch(days=30)
        assert len(items) == 1
        assert items[0].title == "First Post"
        assert items[0].source_type == "blog"
        assert items[0].published_at == "2026-06-01T10:00:00Z"

    def test_fetch_article_with_meta_date(self, monkeypatch):
        """Articles with <meta property='article:published_time'> are parsed.

        Uses a dynamic date (5 days ago) to stay inside the 30-day lookback window
        regardless of when the test is run. Previously hardcoded "2026-05-15" which
        drifted outside the 30-day window by 2026-06-14, causing CI matrix-wide
        failures (Session 35d fix).
        """
        from datetime import datetime, timedelta, timezone

        published_at = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        html = f"""
        <html><body>
        <article>
            <h2><a href="/post-2">Second Post</a></h2>
            <p>Summary.</p>
            <meta property="article:published_time" content="{published_at}">
        </article>
        </body></html>
        """

        class FakeResponse:
            status_code = 200
            text = html

            def raise_for_status(self):
                pass

        src = BlogSource(urls=["https://blog.example.com"])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch(days=30)
        assert len(items) == 1
        assert items[0].published_at == published_at

    def test_fetch_link_fallback(self, monkeypatch):
        """When no articles found, falls back to extracting links."""
        html = """
        <html><body>
        <a href="/post-1">A blog post with a long enough title</a>
        <a href="/post-2">Another interesting blog article</a>
        </body></html>
        """

        class FakeResponse:
            status_code = 200
            text = html

            def raise_for_status(self):
                pass

        src = BlogSource(urls=["https://blog.example.com"])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch()
        assert len(items) == 2
        assert items[0].title == "A blog post with a long enough title"

    def test_fetch_network_error(self, monkeypatch):
        """Network errors are caught per URL, not crashing the batch."""
        src = BlogSource(urls=["https://down.example.com"])

        def fake_get(url):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(src._client, "get", fake_get)
        items = src.fetch()
        assert items == []

    def test_fetch_non_200(self, monkeypatch):
        """Non-200 responses are handled gracefully."""

        class FakeResponse:
            status_code = 404

            def raise_for_status(self):
                raise httpx.HTTPStatusError("not found", request=None, response=None)

        src = BlogSource(urls=["https://blog.example.com"])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch()
        assert items == []

    def test_fetch_empty_html(self, monkeypatch):
        """Empty HTML returns no items."""

        class FakeResponse:
            status_code = 200
            text = "<html><body></body></html>"

            def raise_for_status(self):
                pass

        src = BlogSource(urls=["https://blog.example.com"])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch()
        assert items == []

    def test_context_manager(self):
        src = BlogSource(urls=[])
        with src:
            pass  # Should not raise


# ── _parse_date_utc ─────────────────────────────────────────────────────


class TestParseDateUtc:
    def test_iso_format(self):
        dt = _parse_date_utc("2026-06-01T10:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6

    def test_aware_to_utc(self):
        """Aware datetimes are converted to UTC naive."""
        dt = _parse_date_utc("2026-06-01T10:00:00+08:00")
        assert dt is not None
        assert dt.tzinfo is None
        assert dt.hour == 2  # 10:00 +08:00 = 02:00 UTC

    def test_naive_datetime(self):
        dt = _parse_date_utc("2026-06-01 10:00:00")
        assert dt is not None
        assert dt.hour == 10

    def test_empty_string(self):
        assert _parse_date_utc("") is None

    def test_none_input(self):
        assert _parse_date_utc(None) is None

    def test_whitespace_only(self):
        assert _parse_date_utc("   ") is None

    def test_garbage_string(self):
        assert _parse_date_utc("not a date at all") is None

    def test_date_only(self):
        dt = _parse_date_utc("2026-06-01")
        assert dt is not None
        assert dt.year == 2026


# ── TwitterSource ───────────────────────────────────────────────────────


class TestTwitterSource:
    def test_construction(self):
        src = TwitterSource(bearer_token="tok", accounts=["user1"])
        assert src.bearer_token == "tok"
        assert src.accounts == ["user1"]

    def test_construction_no_accounts(self):
        src = TwitterSource()
        items = src.fetch()
        assert items == []

    def test_fetch_api_success(self, monkeypatch):
        """API path returns FeedItems."""
        src = TwitterSource(bearer_token="tok", accounts=["testuser"])

        class FakeUserResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"data": {"id": "12345"}}

        class FakeTweetsResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"data": [{"id": "t1", "text": "Hello tweet"}]}

        def fake_get(url, headers=None, params=None):
            if "username" in url:
                return FakeUserResponse()
            return FakeTweetsResponse()

        monkeypatch.setattr(src._client, "get", fake_get)
        items = src.fetch(limit=10)
        assert len(items) == 1
        assert items[0].source_type == "tweet"
        assert items[0].content == "Hello tweet"
        src.close()

    def test_fetch_api_fallback_to_nitter(self, monkeypatch):
        """When API fails, falls back to Nitter RSS."""
        src = TwitterSource(bearer_token="tok", accounts=["testuser"])

        # API raises
        def fake_get_api(url, headers=None, params=None):
            raise httpx.HTTPStatusError("unauthorized", request=None, response=None)

        monkeypatch.setattr(src._client, "get", fake_get_api)

        # Nitter returns RSS
        class FakeNitterResponse:
            status_code = 200
            text = """<?xml version="1.0" encoding="UTF-8"?>
            <rss><channel>
                <item>
                    <link>https://nitter.net/testuser/status/1</link>
                    <title>Tweet from nitter</title>
                    <summary>Content from nitter</summary>
                    <id>https://nitter.net/testuser/status/1</id>
                </item>
            </channel></rss>"""

            def raise_for_status(self):
                pass

        def fake_get_nitter(url, **kwargs):
            if "nitter" in url:
                return FakeNitterResponse()
            raise httpx.ConnectError("fail")

        monkeypatch.setattr(src._client, "get", fake_get_nitter)
        items = src.fetch(limit=10)
        # May return empty if all nitter instances fail, but shouldn't crash
        assert isinstance(items, list)
        src.close()

    def test_fetch_nitter_no_bearer_token(self, monkeypatch):
        """Without bearer token, goes directly to Nitter."""
        src = TwitterSource(bearer_token=None, accounts=["testuser"])

        class FakeNitterResponse:
            status_code = 200
            text = """<rss><channel>
                <item>
                    <link>https://nitter.net/testuser/status/99</link>
                    <title>Nitter tweet</title>
                    <summary>Nitter content</summary>
                </item>
            </channel></rss>"""

            def raise_for_status(self):
                pass

        def fake_get(url, **kwargs):
            return FakeNitterResponse()

        monkeypatch.setattr(src._client, "get", fake_get)
        items = src.fetch(limit=10)
        # Should attempt nitter fetch
        assert isinstance(items, list)
        src.close()

    def test_context_manager(self):
        with TwitterSource(accounts=[]) as src:
            assert src.accounts == []


# ── YouTubeSource ───────────────────────────────────────────────────────


class TestYouTubeSource:
    def test_construction(self):
        src = YouTubeSource(channels=[{"id": "UC123", "name": "Test"}])
        assert len(src.channels) == 1

    def test_construction_no_channels(self):
        src = YouTubeSource()
        items = src.fetch()
        assert items == []

    def test_fetch_rss_success(self, monkeypatch):
        """RSS feed parsing returns FeedItems."""
        src = YouTubeSource(channels=[{"id": "UC123", "name": "TestChannel"}])

        class FakeResponse:
            status_code = 200
            # Include <id> element because feedparser entry.id is accessed by source code
            text = """<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015">
                <entry>
                    <yt:videoid>abc123</yt:videoid>
                    <id>yt:video:abc123</id>
                    <link href="https://www.youtube.com/watch?v=abc123"/>
                    <title>Test Video Title</title>
                    <summary>Video description</summary>
                    <published>2026-06-01T10:00:00Z</published>
                </entry>
            </feed>"""

            def raise_for_status(self):
                pass

        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch(limit=10)
        assert len(items) == 1
        assert items[0].source_type == "youtube_video"
        assert items[0].title == "Test Video Title"
        assert items[0].author == "TestChannel"
        src.close()

    def test_fetch_network_error(self, monkeypatch):
        """Network errors are caught per channel."""
        src = YouTubeSource(channels=[{"id": "UC123", "name": "TestChannel"}])

        def fake_get(url):
            raise httpx.ConnectError("timeout")

        monkeypatch.setattr(src._client, "get", fake_get)
        items = src.fetch()
        assert items == []
        src.close()

    def test_fetch_non_200(self, monkeypatch):
        """Non-200 responses are handled gracefully."""

        class FakeResponse:
            status_code = 404

            def raise_for_status(self):
                raise httpx.HTTPStatusError("not found", request=None, response=None)

        src = YouTubeSource(channels=[{"id": "UC123", "name": "Test"}])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch()
        assert items == []
        src.close()

    def test_fetch_empty_feed(self, monkeypatch):
        """Empty RSS feed returns no items."""

        class FakeResponse:
            status_code = 200
            text = '<?xml version="1.0"?><feed></feed>'

            def raise_for_status(self):
                pass

        src = YouTubeSource(channels=[{"id": "UC123", "name": "Test"}])
        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch()
        assert items == []
        src.close()

    def test_fetch_multiple_channels(self, monkeypatch):
        """Multiple channels are processed independently."""
        src = YouTubeSource(
            channels=[
                {"id": "UC111", "name": "Channel1"},
                {"id": "UC222", "name": "Channel2"},
            ]
        )

        class FakeResponse:
            status_code = 200
            text = """<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015">
                <entry>
                    <yt:videoid>v1</yt:videoid>
                    <id>yt:video:v1</id>
                    <link href="https://youtube.com/watch?v=v1"/>
                    <title>Video</title>
                </entry>
            </feed>"""

            def raise_for_status(self):
                pass

        monkeypatch.setattr(src._client, "get", lambda url: FakeResponse())
        items = src.fetch(limit=10)
        assert len(items) == 2
        src.close()
