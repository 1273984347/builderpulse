"""Tests for builderpulse.batch.cache — SQLite BatchCache."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

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
            cache.set("https://example.com/fail", "failed", error_code="DOWNLOAD_FAILED")
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

        threads = [threading.Thread(target=worker, args=(f"https://t{i}.com",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3
        assert all(r is not None for r in results)
