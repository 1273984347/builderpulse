"""Tests for content sources."""
from builderpulse.sources.podcast import PodcastSource


def test_podcast_source_creation():
    src = PodcastSource(feeds=["https://example.com/feed.xml"])
    assert len(src.feeds) == 1


def test_podcast_source_empty():
    src = PodcastSource()
    items = src.fetch()
    assert items == []


def test_podcast_source_no_real_fetch():
    """Verify no crash when feeds list is empty."""
    src = PodcastSource(feeds=[])
    result = src.fetch(days=1)
    assert isinstance(result, list)


def test_blog_source_creation():
    from builderpulse.sources.blog import BlogSource

    src = BlogSource(urls=["https://example.com/blog"])
    assert len(src.urls) == 1


def test_blog_source_empty():
    from builderpulse.sources.blog import BlogSource

    src = BlogSource()
    items = src.fetch()
    assert items == []


# ── Twitter source ────────────────────────────────────────────────────


def test_twitter_source_creation():
    from builderpulse.sources.twitter import TwitterSource

    src = TwitterSource(accounts=["karpathy"])
    assert len(src.accounts) == 1


def test_twitter_source_no_token():
    from builderpulse.sources.twitter import TwitterSource

    src = TwitterSource(bearer_token=None, accounts=[])
    items = src.fetch()
    assert items == []


# ── Bilibili source ────────────────────────────────────────────────────


def test_bilibili_source_creation():
    from builderpulse.sources.bilibili import BilibiliSource

    src = BilibiliSource(users=[{"mid": 946974, "name": "3B1B"}])
    assert len(src.users) == 1


def test_bilibili_source_empty():
    from builderpulse.sources.bilibili import BilibiliSource

    src = BilibiliSource()
    assert src.fetch() == []


# ── YouTube source ─────────────────────────────────────────────────────


def test_youtube_source_creation():
    from builderpulse.sources.youtube import YouTubeSource

    src = YouTubeSource(channels=[{"id": "UCxxxx", "name": "Test"}])
    assert len(src.channels) == 1


def test_youtube_source_empty():
    from builderpulse.sources.youtube import YouTubeSource

    src = YouTubeSource()
    assert src.fetch() == []
