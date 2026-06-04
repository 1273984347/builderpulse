"""Tests for MCP tool handlers — bp_transcribe, bp_batch_transcribe, bp_digest, bp_process, bp_fetch_feed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from builderpulse.mcp_server import handle_tool_call


# ── bp_transcribe ───────────────────────────────────────────────────────


class TestBpTranscribe:
    def test_happy_path(self, monkeypatch):
        """Transcribe with mocked pipeline returns transcript data."""
        mock_transcript = MagicMock()
        mock_transcript.text = "Hello world transcript"
        mock_transcript.language = "en"
        mock_transcript.engine = "whisper"
        mock_transcript.word_count = 3

        mock_ctx = MagicMock()
        mock_ctx.error = None
        mock_ctx.transcript = mock_transcript

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx

        # Pipeline is imported inside _handle_transcribe, so patch at the source module
        with patch("builderpulse.core.pipeline.Pipeline", return_value=mock_pipeline):
            result = handle_tool_call("bp_transcribe", {"url": "https://www.youtube.com/watch?v=abc123"})

        assert result["text"] == "Hello world transcript"
        assert result["language"] == "en"
        assert result["engine"] == "whisper"
        assert result["word_count"] == 3

    def test_missing_url(self):
        """Missing required url argument returns error."""
        result = handle_tool_call("bp_transcribe", {})
        assert "error" in result

    def test_pipeline_error(self, monkeypatch):
        """Pipeline error is propagated."""
        mock_ctx = MagicMock()
        mock_ctx.error = "Download failed"
        mock_ctx.transcript = None

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx

        with patch("builderpulse.core.pipeline.Pipeline", return_value=mock_pipeline):
            result = handle_tool_call("bp_transcribe", {"url": "https://www.youtube.com/watch?v=abc123"})

        assert "error" in result
        assert result["error"] == "Download failed"


# ── bp_batch_transcribe ────────────────────────────────────────────────


class TestBpBatchTranscribe:
    def test_returns_stub_response(self):
        """bp_batch_transcribe returns not_implemented stub."""
        result = handle_tool_call("bp_batch_transcribe", {"user_url": "https://bilibili.com/up/123"})
        assert result["status"] == "not_implemented"
        assert "not yet implemented" in result["message"].lower()

    def test_missing_user_url(self):
        """Missing required user_url returns error."""
        result = handle_tool_call("bp_batch_transcribe", {})
        assert "error" in result


# ── bp_digest ───────────────────────────────────────────────────────────


class TestBpDigest:
    def test_happy_path(self, monkeypatch):
        """Digest with mocked sources returns item count."""
        mock_feed_item = MagicMock()
        mock_feed_item.title = "Test Post"
        mock_feed_item.url = "https://example.com/post"
        mock_feed_item.source_type = "blog"
        mock_feed_item.content = "content"

        mock_cfg = {"sources": {"podcast": {"feeds": []}, "twitter": {"accounts": []}, "blog": {"urls": []}}}

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.podcast.PodcastSource.fetch", return_value=[]):
                with patch("builderpulse.sources.twitter.TwitterSource.fetch", return_value=[]):
                    with patch("builderpulse.sources.blog.BlogSource.fetch", return_value=[mock_feed_item]):
                        result = handle_tool_call("bp_digest", {"sources": "all", "language": "zh", "days": 1})

        assert "item_count" in result
        assert result["item_count"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Test Post"

    def test_empty_sources(self, monkeypatch):
        """All sources empty returns zero items."""
        mock_cfg = {"sources": {"podcast": {"feeds": []}, "twitter": {"accounts": []}, "blog": {"urls": []}}}

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.podcast.PodcastSource.fetch", return_value=[]):
                with patch("builderpulse.sources.twitter.TwitterSource.fetch", return_value=[]):
                    with patch("builderpulse.sources.blog.BlogSource.fetch", return_value=[]):
                        result = handle_tool_call("bp_digest", {})

        assert result["item_count"] == 0

    def test_with_delivery(self, monkeypatch):
        """Digest with deliver parameter attempts delivery."""
        mock_cfg = {"sources": {"podcast": {"feeds": []}, "twitter": {"accounts": []}, "blog": {"urls": []}}}

        mock_channel = MagicMock()
        mock_channel.send.return_value = True

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.podcast.PodcastSource.fetch", return_value=[]):
                with patch("builderpulse.sources.twitter.TwitterSource.fetch", return_value=[]):
                    with patch("builderpulse.sources.blog.BlogSource.fetch", return_value=[]):
                        with patch("builderpulse.deliver.get_channel", return_value=mock_channel):
                            result = handle_tool_call("bp_digest", {"deliver": "telegram"})

        assert result["item_count"] == 0


# ── bp_process ──────────────────────────────────────────────────────────


class TestBpProcess:
    def test_happy_path(self, monkeypatch):
        """Process with mocked pipeline returns summary."""
        mock_transcript = MagicMock()
        mock_transcript.word_count = 100

        mock_ctx = MagicMock()
        mock_ctx.error = None
        mock_ctx.transcript = mock_transcript
        mock_ctx.summary = "This is a summary"
        mock_ctx.delivery_results = {}

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx

        with patch("builderpulse.core.pipeline.Pipeline", return_value=mock_pipeline):
            result = handle_tool_call("bp_process", {"url": "https://www.youtube.com/watch?v=abc"})

        assert result["transcript_words"] == 100
        assert result["summary"] == "This is a summary"

    def test_missing_url(self):
        """Missing required url returns error."""
        result = handle_tool_call("bp_process", {})
        assert "error" in result

    def test_pipeline_error(self, monkeypatch):
        """Pipeline error is propagated."""
        mock_ctx = MagicMock()
        mock_ctx.error = "Transcription failed"

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx

        with patch("builderpulse.core.pipeline.Pipeline", return_value=mock_pipeline):
            result = handle_tool_call("bp_process", {"url": "https://www.youtube.com/watch?v=abc"})

        assert "error" in result
        assert result["error"] == "Transcription failed"


# ── bp_fetch_feed ───────────────────────────────────────────────────────


class TestBpFetchFeed:
    def test_unknown_source(self):
        """Unknown source returns error."""
        result = handle_tool_call("bp_fetch_feed", {"source": "nonexistent"})
        assert "error" in result
        assert "unknown" in result["error"].lower()

    def test_missing_source(self):
        """Missing required source returns error."""
        result = handle_tool_call("bp_fetch_feed", {})
        assert "error" in result

    def test_twitter_source(self, monkeypatch):
        """Twitter feed fetch with mocked config."""
        mock_cfg = {"sources": {"twitter": {"accounts": ["elonmusk"]}}}
        mock_items = [MagicMock(title="Tweet 1", url="https://x.com/elonmusk/status/1", content="Hello", source_type="tweet")]

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.twitter.TwitterSource.fetch", return_value=mock_items):
                result = handle_tool_call("bp_fetch_feed", {"source": "twitter"})

        assert "items" in result
        assert len(result["items"]) == 1

    def test_blog_source(self, monkeypatch):
        """Blog feed fetch with mocked config."""
        mock_cfg = {"sources": {"blog": {"urls": ["https://blog.example.com"]}}}
        mock_items = [MagicMock(title="Post 1", url="https://blog.example.com/post1", content="content", source_type="blog")]

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.blog.BlogSource.fetch", return_value=mock_items):
                result = handle_tool_call("bp_fetch_feed", {"source": "blog"})

        assert "items" in result
        assert len(result["items"]) == 1

    def test_podcast_source(self, monkeypatch):
        """Podcast feed fetch with mocked config."""
        mock_cfg = {"sources": {"podcast": {"feeds": ["https://feed.example.com/rss"]}}}
        mock_items = [MagicMock(title="Episode 1", url="https://pod.example.com/ep1", content="desc", source_type="podcast")]

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.podcast.PodcastSource.fetch", return_value=mock_items):
                result = handle_tool_call("bp_fetch_feed", {"source": "podcast"})

        assert "items" in result

    def test_bilibili_source(self, monkeypatch):
        """Bilibili feed fetch with mocked config."""
        mock_cfg = {"sources": {"bilibili": {"users": ["uid123"]}}}
        mock_items = [MagicMock(title="BV1", url="https://bilibili.com/video/BV1", content="desc", source_type="bilibili_video")]

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value=mock_cfg):
            with patch("builderpulse.sources.bilibili.BilibiliSource.fetch", return_value=mock_items):
                result = handle_tool_call("bp_fetch_feed", {"source": "bilibili"})

        assert "items" in result

    def test_youtube_source(self, monkeypatch):
        """YouTube feed fetch with mocked config."""
        mock_items = [MagicMock(title="Video 1", url="https://youtube.com/watch?v=abc", content="desc", source_type="youtube_video")]

        with patch("builderpulse.core.config_manager.ConfigManager.get_raw", return_value={}):
            with patch("builderpulse.sources.youtube.YouTubeSource.fetch", return_value=mock_items):
                result = handle_tool_call("bp_fetch_feed", {"source": "youtube"})

        assert "items" in result


# ── handle_tool_call general ────────────────────────────────────────────


class TestHandleToolCallGeneral:
    def test_unknown_tool(self):
        """Unknown tool name returns error dict."""
        result = handle_tool_call("bp_nonexistent", {})
        assert "error" in result
        assert "unknown tool" in result["error"].lower()

    def test_list_sources(self):
        """bp_list_sources returns source and channel lists."""
        result = handle_tool_call("bp_list_sources", {})
        assert "sources" in result
        assert "delivery_channels" in result
        assert "twitter" in result["sources"]

    def test_config_show(self):
        """bp_config show returns config dict."""
        result = handle_tool_call("bp_config", {"action": "show"})
        assert "language" in result

    def test_reload_config(self):
        """bp_reload_config returns status."""
        result = handle_tool_call("bp_reload_config", {})
        assert result["status"] == "auto"
