"""Tests for builderpulse.batch.manager — BatchManager._classify_error."""

from __future__ import annotations

from pathlib import Path


from builderpulse.batch.disk_guard import DiskFullError
from builderpulse.batch.manager import BatchManager
from builderpulse.batch.retry import RetryExhausted


class TestClassifyError:
    """_classify_error maps exceptions to ErrorCode values."""

    def test_disk_full_error(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(DiskFullError("disk full"))
        assert code == "BATCH_DISK_FULL"
        mgr.shutdown()

    def test_permission_error(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(PermissionError("forbidden"))
        assert code == "DOWNLOAD_FORBIDDEN"
        mgr.shutdown()

    def test_retry_exhausted_with_connection_error(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        inner = ConnectionError("timeout")
        hist = [(0, inner, 1.0), (1, inner, 2.0), (2, inner, 4.0)]
        exc = RetryExhausted("exhausted", history=hist)
        code = mgr._classify_error(exc)
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_retry_exhausted_with_timeout_error(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        inner = TimeoutError("timed out")
        hist = [(0, inner, 1.0)]
        exc = RetryExhausted("exhausted", history=hist)
        code = mgr._classify_error(exc)
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_default_error(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        code = mgr._classify_error(RuntimeError("something"))
        assert code == "BATCH_ITEM_FAILED"
        mgr.shutdown()

    def test_follows_cause_chain(self, tmp_path: Path) -> None:
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


class TestBatchManagerInit:
    """BatchManager construction."""

    def test_creates_components(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        assert mgr._cache is not None
        assert mgr._disk is not None
        # P1 fix: semaphore/limiter are now created lazily in process_batch_async
        assert mgr._concurrency == 5
        assert mgr._qps == 5.0
        mgr.shutdown()


class TestBatchManagerShutdown:
    """shutdown() closes cache."""

    def test_shutdown_closes_cache(self, tmp_path: Path) -> None:
        mgr = BatchManager(config=None, db_path=tmp_path / "cache.db")
        mgr.shutdown()
        # Should not raise
