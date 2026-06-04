"""Tests for BatchManager.process_batch() — cache hit, disk guard, error classification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from builderpulse.batch.disk_guard import DiskFullError
from builderpulse.batch.manager import BatchManager
from builderpulse.batch.retry import RetryExhausted


class TestProcessBatchSingleUrl:
    """process_batch() with a single URL and mocked pipeline."""

    def test_single_url_success(self, tmp_path, monkeypatch):
        """process_batch returns success result for a single URL."""
        mock_transcript = MagicMock()
        mock_transcript.word_count = 50

        mock_ctx = MagicMock()
        mock_ctx.error = None
        mock_ctx.transcript = mock_transcript
        mock_ctx.summary = "A summary of the video"

        mock_pipeline_cls = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx
        mock_pipeline_cls.return_value = mock_pipeline

        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")

        # Mock disk guard to skip filesystem check
        monkeypatch.setattr(mgr._disk, "check", lambda path: None)

        with patch("builderpulse.core.pipeline.Pipeline", mock_pipeline_cls):
            results = mgr.process_batch(["https://www.youtube.com/watch?v=abc123"])

        assert len(results) == 1
        assert results[0]["status"] == "done"
        assert results[0]["word_count"] == 50
        assert results[0]["summary"] == "A summary of the video"
        mgr.shutdown()

    def test_single_url_pipeline_error(self, tmp_path, monkeypatch):
        """Pipeline error returns failed status."""
        mock_ctx = MagicMock()
        mock_ctx.error = "Download failed"
        mock_ctx.transcript = None

        mock_pipeline_cls = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx
        mock_pipeline_cls.return_value = mock_pipeline

        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")

        monkeypatch.setattr(mgr._disk, "check", lambda path: None)

        with patch("builderpulse.core.pipeline.Pipeline", mock_pipeline_cls):
            results = mgr.process_batch(["https://www.youtube.com/watch?v=abc123"])

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert results[0]["error"] == "Download failed"
        mgr.shutdown()


class TestProcessBatchCacheHit:
    """Second call should use cache."""

    def test_cache_hit_returns_cached_result(self, tmp_path, monkeypatch):
        """When URL is already cached with status 'done', returns cached result."""
        mock_transcript = MagicMock()
        mock_transcript.word_count = 50

        mock_ctx = MagicMock()
        mock_ctx.error = None
        mock_ctx.transcript = mock_transcript
        mock_ctx.summary = "Cached summary"

        mock_pipeline_cls = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_ctx
        mock_pipeline_cls.return_value = mock_pipeline

        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")

        # Mock disk guard to skip filesystem check
        monkeypatch.setattr(mgr._disk, "check", lambda path: None)

        with patch("builderpulse.core.pipeline.Pipeline", mock_pipeline_cls):
            # First call — runs pipeline
            results1 = mgr.process_batch(["https://www.youtube.com/watch?v=abc123"])
            # Second call — should hit cache
            results2 = mgr.process_batch(["https://www.youtube.com/watch?v=abc123"])

        assert results1[0]["status"] == "done"
        assert results2[0]["status"] == "done"
        # Pipeline should only be called once (first time)
        assert mock_pipeline.run.call_count == 1
        mgr.shutdown()


class TestProcessBatchDiskGuard:
    """Disk guard integration."""

    def test_disk_full_raises(self, tmp_path, monkeypatch):
        """DiskFullError from DiskGuard is caught and classified."""
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")

        # Patch disk guard to raise DiskFullError
        def fake_check(path):
            raise DiskFullError("disk full")

        monkeypatch.setattr(mgr._disk, "check", fake_check)

        results = mgr.process_batch(["https://www.youtube.com/watch?v=abc123"])
        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert results[0]["error_code"] == "BATCH_DISK_FULL"
        mgr.shutdown()


class TestProcessBatchErrorClassification:
    """Error classification for each exception type."""

    def test_disk_full_error(self, tmp_path):
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(DiskFullError("no space"))
        assert code == "BATCH_DISK_FULL"
        mgr.shutdown()

    def test_permission_error(self, tmp_path):
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(PermissionError("forbidden"))
        assert code == "DOWNLOAD_FORBIDDEN"
        mgr.shutdown()

    def test_retry_exhausted_connection(self, tmp_path):
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        inner = ConnectionError("timeout")
        hist = [(0, inner, 1.0), (1, inner, 2.0)]
        exc = RetryExhausted("exhausted", history=hist)
        code = mgr._classify_error(exc)
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_retry_exhausted_timeout(self, tmp_path):
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        inner = TimeoutError("timed out")
        hist = [(0, inner, 1.0)]
        exc = RetryExhausted("exhausted", history=hist)
        code = mgr._classify_error(exc)
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_generic_runtime_error(self, tmp_path):
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(RuntimeError("something"))
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_cause_chain_disk_full(self, tmp_path):
        """DiskFullError wrapped in RuntimeError is detected."""
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        try:
            try:
                raise DiskFullError("no space")
            except DiskFullError as inner:
                raise RuntimeError("wrapped") from inner
        except RuntimeError as outer:
            code = mgr._classify_error(outer)
        assert code == "BATCH_DISK_FULL"
        mgr.shutdown()

    def test_cause_chain_permission(self, tmp_path):
        """PermissionError wrapped in RuntimeError is detected."""
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        try:
            try:
                raise PermissionError("denied")
            except PermissionError as inner:
                raise RuntimeError("wrapped") from inner
        except RuntimeError as outer:
            code = mgr._classify_error(outer)
        assert code == "DOWNLOAD_FORBIDDEN"
        mgr.shutdown()


class TestProcessBatchMultipleUrls:
    """process_batch() with multiple URLs."""

    def test_mixed_success_and_failure(self, tmp_path, monkeypatch):
        """One URL succeeds, one fails — both are reported."""
        call_count = {"n": 0}

        def fake_run(source):
            call_count["n"] += 1
            if call_count["n"] == 1:
                mock_ctx = MagicMock()
                mock_ctx.error = None
                mock_transcript = MagicMock()
                mock_transcript.word_count = 30
                mock_ctx.transcript = mock_transcript
                mock_ctx.summary = "Summary"
                return mock_ctx
            else:
                mock_ctx = MagicMock()
                mock_ctx.error = "Transcription failed"
                mock_ctx.transcript = None
                return mock_ctx

        mock_pipeline_cls = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.side_effect = fake_run
        mock_pipeline_cls.return_value = mock_pipeline

        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")

        # Mock disk guard to skip filesystem check
        monkeypatch.setattr(mgr._disk, "check", lambda path: None)

        with patch("builderpulse.core.pipeline.Pipeline", mock_pipeline_cls):
            results = mgr.process_batch([
                "https://www.youtube.com/watch?v=abc",
                "https://www.youtube.com/watch?v=def",
            ])

        assert len(results) == 2
        assert results[0]["status"] == "done"
        assert results[1]["status"] == "failed"
        mgr.shutdown()
