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
