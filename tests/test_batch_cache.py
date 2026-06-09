"""Tests for builderpulse.batch.cache — SQLite BatchCache."""

from __future__ import annotations

import threading
from pathlib import Path


from builderpulse.batch.cache import BatchCache


class TestBatchCacheCRUD:
    """Basic get/set operations."""

    def test_set_and_get(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        with BatchCache(db) as cache:
            cache.set("https://example.com/video1", "done", result={"title": "Test"})
            row = cache.get("https://example.com/video1")
        assert row is not None
        assert row["status"] == "done"
        assert row["result"] is not None

    def test_get_miss_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        with BatchCache(db) as cache:
            assert cache.get("https://example.com/missing") is None

    def test_set_with_error(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        with BatchCache(db) as cache:
            cache.set(
                "https://example.com/fail", "failed", error_code="DOWNLOAD_FAILED"
            )
            row = cache.get("https://example.com/fail")
        assert row is not None
        assert row["status"] == "failed"
        assert row["error_code"] == "DOWNLOAD_FAILED"

    def test_upsert_updates_existing(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        with BatchCache(db) as cache:
            cache.set("https://example.com/v1", "pending")
            cache.set("https://example.com/v1", "done", result={"ok": True})
            row = cache.get("https://example.com/v1")
        assert row["status"] == "done"


class TestBatchCacheContextManager:
    """__enter__ / __exit__ behavior."""

    def test_context_manager_closes(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        cache = BatchCache(db)
        with cache:
            cache.set("https://example.com/x", "done")
        # After exit, the thread-local connection should be closed
        # Accessing _get_conn should create a new one (no error)
        cache.close()


class TestBatchCacheTTL:
    """cleanup() removes old entries."""

    def test_cleanup_removes_old(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        with BatchCache(db) as cache:
            # Insert with a fake old timestamp
            cache.set("https://example.com/old", "done")
            # Manually backdate the created_at
            cache._get_conn().execute(
                "UPDATE cache SET created_at = datetime('now', '-10 days') WHERE url_hash = ?",
                (cache._hash_url("https://example.com/old"),),
            )
            cache.set("https://example.com/new", "done")
            removed = cache.cleanup(max_age_days=7)
        assert removed == 1
        with BatchCache(db) as cache2:
            assert cache2.get("https://example.com/old") is None
            assert cache2.get("https://example.com/new") is not None


class TestBatchCacheCloseAll:
    """close_all() classmethod."""

    def test_close_all(self, tmp_path: Path) -> None:
        c1 = BatchCache(tmp_path / "a.db")
        c2 = BatchCache(tmp_path / "b.db")
        with c1:
            c1.set("https://a.com", "done")
        with c2:
            c2.set("https://b.com", "done")
        # Should not raise
        BatchCache.close_all()


class TestBatchCacheThreadLocal:
    """Thread-local connections work correctly."""

    def test_thread_local_connections(self, tmp_path: Path) -> None:
        db = tmp_path / "cache.db"
        results = []

        def worker(url: str) -> None:
            with BatchCache(db) as cache:
                cache.set(url, "done", result={"thread": url})
                row = cache.get(url)
                results.append(row)

        threads = [
            threading.Thread(target=worker, args=(f"https://t{i}.com",))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3
        assert all(r is not None for r in results)


class TestBatchCacheConcurrency:
    """High-contention multi-thread writes must not raise database is locked.

    Regression for the 2026-06-09 CI flake on test_thread_local_connections
    (Python 3.10 ubuntu: 1/9 runs fail with OperationalError: database is locked).

    Root cause: SQLite's default busy_timeout=0 means a writer that finds the
    WAL file locked raises immediately. Under high contention (3+ writers),
    exactly one thread will lose the race every time. Fix: PRAGMA busy_timeout
    in _get_conn() makes SQLite wait up to N ms for the lock instead of failing.

    This test stresses 20 threads x 50 writes = 1000 total writes on a single
    shared SQLite file. Without busy_timeout, this fails ~85% of runs even on
    Windows. With busy_timeout=5000, it must complete in ~1s with 0 errors.
    """

    def test_high_contention_writes_succeed(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "cache.db"
        errors: list[str] = []
        error_lock = threading.Lock()
        N_THREADS = 20
        N_WRITES = 50

        def worker(tid: int) -> None:
            try:
                with BatchCache(db) as cache:
                    for i in range(N_WRITES):
                        cache.set(
                            f"https://t{tid}.com/{i}",
                            "done",
                            result={"tid": tid, "i": i},
                        )
            except Exception as e:
                with error_lock:
                    errors.append(f"t{tid}: {type(e).__name__}: {e}")

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(N_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], (
            f"{len(errors)}/{N_THREADS} threads failed:\n" + "\n".join(errors[:5])
        )

        # Sanity: all 1000 rows landed
        with BatchCache(db) as cache:
            for tid in range(N_THREADS):
                for i in range(N_WRITES):
                    assert cache.get(f"https://t{tid}.com/{i}") is not None

    def test_busy_timeout_is_set_on_connections(
        self, tmp_path: Path
    ) -> None:
        """Defends against future code changes that might drop the PRAGMA.

        Each new BatchCache connection must have busy_timeout > 0, otherwise
        the high-contention test above will fail. If you change _get_conn(),
        do not remove this PRAGMA without re-running the stress test on Linux.
        """
        db = tmp_path / "cache.db"
        with BatchCache(db):
            seen: list[int] = []
            seen_lock = threading.Lock()

            def probe() -> None:
                with BatchCache(db) as c2:
                    val = c2._get_conn().execute("PRAGMA busy_timeout").fetchone()[0]
                    with seen_lock:
                        seen.append(val)

            t = threading.Thread(target=probe)
            t.start()
            t.join()

        assert seen, "probe thread did not run"
        assert all(v > 0 for v in seen), f"busy_timeout not set: {seen}"
