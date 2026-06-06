"""Tests for builderpulse.core.models dataclasses."""

import pytest

from builderpulse.core.models import (
    SourceRef,
    DownloadResult,
    TranscriptResult,
    FeedItem,
)


def test_source_ref_video():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ref = SourceRef.from_url(url)
    assert ref.source_type == "youtube"
    assert ref.native_id == "dQw4w9WgXcQ"
    assert ref.idem_key == "youtube:dQw4w9WgXcQ"


def test_source_ref_bilibili():
    url = "https://www.bilibili.com/video/BV1xx411c7mD/"
    ref = SourceRef.from_url(url)
    assert ref.source_type == "bilibili"
    assert "BV" in ref.native_id
    assert ref.native_id.startswith("BV")


def test_source_ref_douyin():
    url = "https://www.douyin.com/video/7123456789012345678"
    ref = SourceRef.from_url(url)
    assert ref.source_type == "douyin"


def test_source_ref_twitter():
    url = "https://x.com/elonmusk/status/1234567890123456789"
    ref = SourceRef.from_url(url)
    assert ref.source_type == "twitter"
    assert ref.native_id == "1234567890123456789"


def test_source_ref_twitter_no_status():
    import pytest

    with pytest.raises(ValueError, match="Cannot extract tweet ID"):
        SourceRef.from_url("https://x.com/elonmusk")


def test_source_ref_local_file():
    ref = SourceRef.from_url("/path/to/video.mp4")
    assert ref.source_type == "local"
    assert ref.native_id == "/path/to/video.mp4"


def test_download_result():
    result = DownloadResult(
        path="/tmp/video.mp4",
        source_type="youtube",
        native_id="dQw4w9WgXcQ",
        title="Test Video",
        duration=212.5,
    )
    assert result.path == "/tmp/video.mp4"
    assert result.source_type == "youtube"
    assert result.native_id == "dQw4w9WgXcQ"
    assert result.title == "Test Video"
    assert result.duration == 212.5


def test_transcript_result():
    result = TranscriptResult(
        text="Hello world this is a test transcript",
        language="en",
        engine="whisper",
        segments=[{"start": 0.0, "end": 1.0, "text": "Hello world"}],
    )
    assert result.word_count == 7
    assert result.language == "en"
    assert result.engine == "whisper"
    assert len(result.segments) == 1


def test_feed_item():
    item = FeedItem(
        source_type="youtube",
        source_id="dQw4w9WgXcQ",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Test Video",
        content="Some content here",
        author="Test Author",
    )
    assert item.idem_key == "youtube:dQw4w9WgXcQ"
    assert item.published_at is None
    assert item.metadata == {}


# ── SourceRef.from_url() edge cases ────────────────────────────────────


class TestSourceRefEdgeCases:
    """Edge cases for SourceRef.from_url()."""

    def test_youtu_be_short_url(self):
        """youtu.be short URL extracts video ID correctly."""
        ref = SourceRef.from_url("https://youtu.be/dQw4w9WgXcQ")
        assert ref.source_type == "youtube"
        assert ref.native_id == "dQw4w9WgXcQ"

    def test_youtube_mobile_url(self):
        """m.youtube.com URL is recognized."""
        ref = SourceRef.from_url("https://m.youtube.com/watch?v=abc123")
        assert ref.source_type == "youtube"
        assert ref.native_id == "abc123"

    def test_youtube_no_video_id(self):
        """YouTube URL without v= parameter has empty native_id."""
        ref = SourceRef.from_url("https://www.youtube.com/results?search_query=test")
        assert ref.source_type == "youtube"
        assert ref.native_id == ""

    def test_url_with_unicode_path(self):
        """URL with unicode characters is handled."""
        ref = SourceRef.from_url(
            "https://www.bilibili.com/video/BV1xx411c7mD/?title=测试"
        )
        assert ref.source_type == "bilibili"
        assert "BV" in ref.native_id

    def test_url_with_credentials(self):
        """URL with user:pass@host is parsed without error."""
        ref = SourceRef.from_url("https://user:pass@bilibili.com/video/BV1xx411c7mD/")
        assert ref.source_type == "bilibili"

    def test_url_with_no_path(self):
        """URL with no path falls back to web."""
        ref = SourceRef.from_url("https://example.com")
        assert ref.source_type == "web"

    def test_url_with_empty_path(self):
        """URL with empty path falls back to web."""
        ref = SourceRef.from_url("https://example.com/")
        assert ref.source_type == "web"

    def test_local_file_absolute(self):
        """Absolute local file path is recognized."""
        ref = SourceRef.from_url("/home/user/video.mp4")
        assert ref.source_type == "local"
        assert ref.native_id == "/home/user/video.mp4"

    def test_generic_web_url(self):
        """Unknown domain falls back to web type."""
        ref = SourceRef.from_url("https://news.ycombinator.com/item?id=12345")
        assert ref.source_type == "web"
        assert ref.url == "https://news.ycombinator.com/item?id=12345"

    def test_twitter_url_with_trailing_slash(self):
        """Twitter URL with trailing slash still extracts tweet ID."""
        ref = SourceRef.from_url("https://x.com/user/status/1234567890/")
        assert ref.source_type == "twitter"
        assert ref.native_id == "1234567890"

    def test_twitter_url_no_status_raises(self):
        """Twitter URL without status/ segment raises ValueError."""
        with pytest.raises(ValueError, match="Cannot extract tweet ID"):
            SourceRef.from_url("https://x.com/elonmusk")

    def test_bilibili_short_url(self):
        """b23.tv short URL falls back to web (not recognized as bilibili)."""
        ref = SourceRef.from_url("https://b23.tv/BV1xx411c7mD")
        assert ref.source_type == "web"  # b23.tv is not in bilibili.com check

    def test_idem_key_consistency(self):
        """Same URL always produces the same idem_key."""
        ref1 = SourceRef.from_url("https://www.youtube.com/watch?v=abc123")
        ref2 = SourceRef.from_url("https://www.youtube.com/watch?v=abc123")
        assert ref1.idem_key == ref2.idem_key

    def test_title_parameter(self):
        """Title parameter is stored."""
        ref = SourceRef.from_url(
            "https://www.youtube.com/watch?v=abc", title="My Video"
        )
        assert ref.title == "My Video"

    def test_title_default_none(self):
        """Title defaults to None."""
        ref = SourceRef.from_url("https://www.youtube.com/watch?v=abc")
        assert ref.title is None
