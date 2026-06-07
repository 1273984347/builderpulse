"""Tests for builderpulse.core.state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from builderpulse.core.state import (
    MAX_ATTEMPTS,
    State,
    make_idem_key,
    make_idem_key_from_url,
    normalize_url,
)


@pytest.fixture(autouse=True)
def reset_initialized_paths():
    """Clear _initialized_paths before and after each test to prevent leaks."""
    State._initialized_paths.clear()
    yield
    State._initialized_paths.clear()


@pytest.fixture
def tmp_state(tmp_path):
    """Create a State instance with a temporary database."""
    db_path = tmp_path / "test_state.db"
    lock_path = tmp_path / ".lock"
    state = State(db_path=db_path, lock_path=lock_path)
    yield state
    state.close()


# ── Idempotent key tests ──────────────────────────────────────────────


class TestIdemKey:
    def test_make_idem_key(self):
        assert make_idem_key("tweet", "12345") == "tweet:12345"
        assert (
            make_idem_key("bilibili_video", "BV1Nd596vEyU")
            == "bilibili_video:BV1Nd596vEyU"
        )
        assert make_idem_key("podcast", "abc-def-ghi") == "podcast:abc-def-ghi"

    def test_make_idem_key_from_url(self):
        key1 = make_idem_key_from_url(
            "https://example.com/article?utm_source=twitter&id=1"
        )
        key2 = make_idem_key_from_url("https://example.com/article?id=1")
        # utm_ params stripped → same key
        assert key1 == key2

    def test_make_idem_key_from_url_trailing_slash(self):
        key1 = make_idem_key_from_url("https://example.com/article/")
        key2 = make_idem_key_from_url("https://example.com/article")
        assert key1 == key2

    def test_make_idem_key_from_url_case_insensitive(self):
        key1 = make_idem_key_from_url("https://Example.COM/Article")
        key2 = make_idem_key_from_url("https://example.com/Article")
        assert key1 == key2

    def test_make_idem_key_from_url_different_urls(self):
        key1 = make_idem_key_from_url("https://example.com/a")
        key2 = make_idem_key_from_url("https://example.com/b")
        assert key1 != key2

    def test_normalize_url(self):
        assert (
            normalize_url("https://EXAMPLE.com/path/?utm_source=x&foo=bar")
            == "https://example.com/path?foo=bar"
        )

    def test_normalize_url_strips_fragment(self):
        assert (
            normalize_url("https://example.com/path#section")
            == "https://example.com/path"
        )


# ── Schema tests ──────────────────────────────────────────────────────


class TestSchema:
    def test_tables_created(self, tmp_state):
        tables = tmp_state._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "processed_items" in names
        assert "feed_cursors" in names
        assert "delivery_log" in names
        assert "batch_runs" in names
        assert "batch_items" in names

    def test_wal_mode(self, tmp_state):
        mode = tmp_state._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_schema_version(self, tmp_state):
        version = tmp_state._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 1

    def test_idempotent_init(self, tmp_state):
        """Calling __init__ twice should not fail."""
        tmp_state._init_schema(tmp_state._conn)  # should not raise


# ── CRUD tests ────────────────────────────────────────────────────────


class TestProcessedItems:
    def test_mark_and_check(self, tmp_state):
        inserted = tmp_state.mark_processed(
            idem_key="tweet:123",
            source_type="tweet",
            source_id="123",
            url="https://x.com/user/status/123",
            status="done",
        )
        assert inserted is True  # P1 fix: returns True on first insert
        assert tmp_state.is_processed("tweet:123")
        assert not tmp_state.is_processed("tweet:456")

    def test_mark_processed_returns_false_on_duplicate(self, tmp_state):
        """P1 fix: mark_processed returns False when item already exists (no TOCTOU)."""
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        inserted = tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        assert inserted is False

    def test_get_item(self, tmp_state):
        tmp_state.mark_processed(
            idem_key="bvid:BV123",
            source_type="bilibili_video",
            source_id="BV123",
            url="https://bilibili.com/video/BV123",
            status="downloading",
            output_path="downloads/BV123.mp4",
        )
        item = tmp_state.get_item("bvid:BV123")
        assert item is not None
        assert item.source_type == "bilibili_video"
        assert item.status == "downloading"
        assert item.output_path == "downloads/BV123.mp4"
        assert item.attempts == 0

    def test_get_item_not_found(self, tmp_state):
        assert tmp_state.get_item("nonexistent") is None

    def test_upsert_updates_existing(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "pending")
        tmp_state.mark_processed("k:v", "t", "id", "url", "done", output_path="out.md")
        item = tmp_state.get_item("k:v")
        assert item.status == "done"
        assert item.output_path == "out.md"

    def test_invalid_status_raises(self, tmp_state):
        with pytest.raises(ValueError, match="Invalid status"):
            tmp_state.mark_processed("k:v", "t", "id", "url", "bogus")


# ── State machine tests ───────────────────────────────────────────────


class TestStateMachine:
    def test_valid_transition(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "pending")
        tmp_state.transition("k:v", "downloading")
        assert tmp_state.get_item("k:v").status == "downloading"

    def test_invalid_transition_raises(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        with pytest.raises(ValueError, match="Invalid transition"):
            tmp_state.transition("k:v", "downloading")

    def test_terminal_state_no_escape(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        with pytest.raises(ValueError):
            tmp_state.transition("k:v", "pending")

    def test_failed_increments_attempts(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "downloading")
        tmp_state.transition("k:v", "failed", error="timeout")
        item = tmp_state.get_item("k:v")
        assert item.status == "failed"
        assert item.attempts == 1
        assert item.error == "timeout"

    def test_permanently_failed_after_max_attempts(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "downloading")
        for i in range(MAX_ATTEMPTS):
            current = tmp_state.get_item("k:v").status
            if current == "permanently_failed":
                break
            # Cycle: downloading → failed → pending → downloading
            tmp_state.transition("k:v", "failed", error=f"attempt {i + 1}")
            current = tmp_state.get_item("k:v").status
            if current == "permanently_failed":
                break
            tmp_state.transition("k:v", "pending")
            tmp_state.transition("k:v", "downloading")
        assert tmp_state.get_item("k:v").status == "permanently_failed"
        assert tmp_state.get_item("k:v").attempts == MAX_ATTEMPTS

    def test_transition_not_found_raises(self, tmp_state):
        with pytest.raises(KeyError):
            tmp_state.transition("nonexistent", "downloading")

    def test_transition_updates_output_path(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "transcribing")
        tmp_state.transition("k:v", "done", output_path="output/transcript.md")
        assert tmp_state.get_item("k:v").output_path == "output/transcript.md"


# ── Crash recovery tests ──────────────────────────────────────────────


class TestRecovery:
    def test_recover_stale_items(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "transcribing")
        # Manually set updated_at to 2 hours ago
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        tmp_state._conn.execute(
            "UPDATE processed_items SET updated_at = ? WHERE idem_key = ?",
            (two_hours_ago, "k:v"),
        )
        count = tmp_state.recover()
        assert count == 1
        assert tmp_state.get_item("k:v").status == "pending"

    def test_recover_ignores_terminal_states(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        tmp_state._conn.execute(
            "UPDATE processed_items SET updated_at = ? WHERE idem_key = ?",
            (two_hours_ago, "k:v"),
        )
        count = tmp_state.recover()
        assert count == 0
        assert tmp_state.get_item("k:v").status == "done"

    def test_recover_ignores_fresh_items(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "transcribing")
        count = tmp_state.recover()
        assert count == 0
        assert tmp_state.get_item("k:v").status == "transcribing"


# ── Feed cursor tests ─────────────────────────────────────────────────


class TestFeedCursors:
    def test_get_cursor_not_found(self, tmp_state):
        assert tmp_state.get_cursor("twitter", "karpathy") is None

    def test_update_and_get_cursor(self, tmp_state):
        tmp_state.update_cursor("twitter", "karpathy", "2056626964090466469")
        cursor = tmp_state.get_cursor("twitter", "karpathy")
        assert cursor is not None
        assert cursor.last_seen_id == "2056626964090466469"
        assert cursor.last_seen_at is not None

    def test_cursor_upsert(self, tmp_state):
        tmp_state.update_cursor("twitter", "karpathy", "100")
        tmp_state.update_cursor("twitter", "karpathy", "200")
        cursor = tmp_state.get_cursor("twitter", "karpathy")
        assert cursor.last_seen_id == "200"

    def test_cursor_no_regression(self, tmp_state):
        """P1 fix: cursor must not regress when a slower worker finishes."""
        tmp_state.update_cursor("twitter", "karpathy", "200")
        tmp_state.update_cursor("twitter", "karpathy", "100")  # should be no-op
        cursor = tmp_state.get_cursor("twitter", "karpathy")
        assert cursor.last_seen_id == "200"  # NOT "100"

    def test_cursor_non_numeric_id(self, tmp_state):
        """Non-numeric IDs (RSS GUIDs, BV numbers) use string comparison."""
        tmp_state.update_cursor("podcast", "feed1", "guid-abc-123")
        tmp_state.update_cursor("podcast", "feed1", "guid-abc-456")
        cursor = tmp_state.get_cursor("podcast", "feed1")
        assert cursor.last_seen_id == "guid-abc-456"


# ── Delivery log tests ────────────────────────────────────────────────


class TestDeliveryLog:
    def test_record_and_check(self, tmp_state):
        digest_id = State.make_digest_id("content", ["twitter"], "2026-06-03")
        tmp_state.record_delivery(digest_id, "telegram", "success")
        assert tmp_state.was_delivered(digest_id, "telegram")
        assert not tmp_state.was_delivered(digest_id, "email")

    def test_not_delivered_on_failure(self, tmp_state):
        digest_id = State.make_digest_id("content", ["twitter"], "2026-06-03")
        tmp_state.record_delivery(digest_id, "telegram", "failed")
        assert not tmp_state.was_delivered(digest_id, "telegram")

    def test_digest_id_deterministic(self):
        d1 = State.make_digest_id("hello", ["a", "b"], "w1")
        d2 = State.make_digest_id("hello", ["b", "a"], "w1")  # sorted
        d3 = State.make_digest_id("hello", ["a", "b"], "w2")  # different window
        assert d1 == d2
        assert d1 != d3


# ── Batch tests ───────────────────────────────────────────────────────


class TestBatch:
    def test_start_batch(self, tmp_state):
        run_id = tmp_state.start_batch(
            "https://douyin.com/user/123", ["url1", "url2", "url3"]
        )
        assert len(run_id) == 12
        run = tmp_state.get_batch_run(run_id)
        assert run is not None
        assert run.total == 3
        assert run.state == "running"

    def test_update_batch_item(self, tmp_state):
        run_id = tmp_state.start_batch("url", ["a", "b"])
        tmp_state.update_batch_item(run_id, "a", "done", output_path="out.md")
        run = tmp_state.get_batch_run(run_id)
        assert run.completed == 1

    def test_finish_batch(self, tmp_state):
        run_id = tmp_state.start_batch("url", ["a"])
        tmp_state.finish_batch(run_id, "completed")
        run = tmp_state.get_batch_run(run_id)
        assert run.state == "completed"
        assert run.finished_at is not None

    def test_batch_not_found(self, tmp_state):
        assert tmp_state.get_batch_run("nonexistent") is None


# ── Stats / inspect tests ─────────────────────────────────────────────


class TestInspection:
    def test_stats(self, tmp_state):
        tmp_state.mark_processed("k1", "t", "1", "u1", "done")
        tmp_state.mark_processed("k2", "t", "2", "u2", "pending")
        stats = tmp_state.stats()
        assert stats["items"]["done"] == 1
        assert stats["items"]["pending"] == 1
        assert stats["total_items"] == 2
        assert stats["db_path"] == str(tmp_state._db_path)

    def test_inspect(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        info = tmp_state.inspect("k:v")
        assert info is not None
        assert info["status"] == "done"
        assert info["source_id"] == "id"

    def test_inspect_not_found(self, tmp_state):
        assert tmp_state.inspect("nonexistent") is None


# ── Cleanup tests ─────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_old_items(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        # Set updated_at to 30 days ago
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        tmp_state._conn.execute(
            "UPDATE processed_items SET updated_at = ? WHERE idem_key = ?",
            (old, "k:v"),
        )
        count = tmp_state.cleanup(max_age_days=14)
        assert count == 1
        assert not tmp_state.is_processed("k:v")

    def test_cleanup_keeps_recent(self, tmp_state):
        tmp_state.mark_processed("k:v", "t", "id", "url", "done")
        count = tmp_state.cleanup(max_age_days=14)
        assert count == 0
        assert tmp_state.is_processed("k:v")


# ── Cursor boundary tests (v2.0.1) ──────────────────────────────────
# Cursor is an opaque string — no validation should reject any value.
# Some platforms use UUIDs, base64 tokens, emoji, CJK chars, etc.


class TestCursorBoundary:
    """Guard against future validation that would break legitimate cursors."""

    def test_cursor_non_numeric_string_accepted(self, tmp_state):
        """Non-numeric cursors (RSS GUIDs, BV numbers, opaque tokens) are stored as-is."""
        tmp_state.update_cursor("podcast", "feed1", "not-a-number-12345")
        cursor = tmp_state.get_cursor("podcast", "feed1")
        assert cursor is not None
        assert cursor.last_seen_id == "not-a-number-12345"

    def test_cursor_empty_string_accepted(self, tmp_state):
        """Empty string is a valid cursor (semantically 'start from beginning')."""
        tmp_state.update_cursor("rss", "empty-feed", "")
        cursor = tmp_state.get_cursor("rss", "empty-feed")
        assert cursor is not None
        assert cursor.last_seen_id == ""

    def test_cursor_unicode_accepted(self, tmp_state):
        """Unicode cursors (emoji, CJK, accented chars) are stored without corruption."""
        opaque = "🚀-cursor-中文-naïve-Ω"
        tmp_state.update_cursor("wechat", "acc", opaque)
        cursor = tmp_state.get_cursor("wechat", "acc")
        assert cursor is not None
        assert cursor.last_seen_id == opaque

    def test_cursor_very_long_string_accepted(self, tmp_state):
        """Long cursors (UUIDs, base64 tokens, signed pagination cursors) round-trip intact."""
        long_cursor = "x" * 10000
        tmp_state.update_cursor("api", "paged", long_cursor)
        cursor = tmp_state.get_cursor("api", "paged")
        assert cursor is not None
        assert cursor.last_seen_id == long_cursor
        assert len(cursor.last_seen_id) == 10000

    def test_cursor_none_still_works(self, tmp_state):
        """No cursor written for a (source, account) → get_cursor returns None (no pagination)."""
        cursor = tmp_state.get_cursor("never", "set")
        assert cursor is None
