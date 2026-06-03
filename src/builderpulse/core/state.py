"""
BuilderPulse state management — SQLite-backed, thread-safe, crash-recoverable.

4 tables: processed_items, feed_cursors, delivery_log, batch_runs + batch_items.
WAL mode for concurrent reads. Advisory file lock for CLI/MCP/cron safety.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────

_SCHEMA_VERSION = 1
_DEFAULT_DB_PATH = Path.home() / ".builderpulse" / "state.db"
_DEFAULT_LOCK_PATH = Path.home() / ".builderpulse" / ".lock"

VALID_STATUSES = {
    "pending",
    "downloading",
    "transcribing",
    "summarizing",
    "delivering",
    "done",
    "failed",
    "permanently_failed",
}

VALID_TRANSITIONS = {
    "pending": {"downloading", "failed"},
    "downloading": {"transcribing", "failed"},
    "transcribing": {"summarizing", "delivering", "done", "failed"},
    "summarizing": {"delivering", "done", "failed"},
    "delivering": {"done", "failed"},
    "done": set(),  # terminal
    "failed": {"pending", "permanently_failed"},  # retry or give up
    "permanently_failed": set(),  # terminal
}

MAX_ATTEMPTS = 3
STALE_THRESHOLD_SEC = 3600  # 1 hour

# Backoff intervals: attempt 1 → 5min, attempt 2 → 30min, attempt 3 → 2h
BACKOFF_INTERVALS = [300, 1800, 7200]


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class Item:
    idem_key: str
    source_type: str
    source_id: str
    url: str
    status: str
    output_path: Optional[str]
    error: Optional[str]
    attempts: int
    created_at: str
    updated_at: str


@dataclass
class Cursor:
    source_type: str
    account: str
    last_seen_id: Optional[str]
    last_seen_at: Optional[str]


@dataclass
class BatchRun:
    run_id: str
    user_url: str
    total: int
    completed: int
    failed: int
    state: str
    started_at: str
    finished_at: Optional[str]


# ── Idempotent key construction ───────────────────────────────────────


def make_idem_key(source_type: str, native_id: str) -> str:
    """Build idempotent key from source type + native ID.

    Native IDs are stable identifiers assigned by the source platform:
    - tweet_id (numeric string, never changes)
    - bvid (BV format, stable; avid is NOT stable)
    - RSS <guid> (not URL, guids are the real stable ID)
    - blog URL (normalized + hashed)
    """
    return f"{source_type}:{native_id}"


def make_idem_key_from_url(url: str) -> str:
    """Build idempotent key from URL when no native ID is available.

    Normalizes the URL first (strip utm_ params, trailing slash, lowercase host)
    so the same content with different tracking params produces the same key.
    """
    norm = normalize_url(url)
    digest = hashlib.sha256(norm.encode()).hexdigest()[:16]
    return f"url:{digest}"


def normalize_url(url: str) -> str:
    """Normalize URL for stable hashing.

    - Lowercase scheme + host
    - Remove trailing slash from path
    - Strip utm_* and tracking query params
    - Remove fragment
    """
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    # Strip tracking params
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in params.items() if not k.startswith("utm_")}
    query = urlencode(filtered, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


# ── State class ───────────────────────────────────────────────────────


class State:
    """SQLite-backed state manager.

    Usage:
        state = State()  # default path ~/.builderpulse/state.db
        state = State(Path("/custom/path/state.db"))

    Thread-safe via WAL mode. Process-safe via advisory file lock.
    P2 fix: _initialized_paths prevents multiple instances from running
    recover() on the same DB in the same process.
    """

    _initialized_paths: set[str] = set()  # P2 fix: per-process dedup

    def __init__(
        self,
        db_path: Optional[Path] = None,
        lock_path: Optional[Path] = None,
    ):
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._lock_path = lock_path or _DEFAULT_LOCK_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self._db_path),
            isolation_level=None,  # autocommit for explicit transaction control
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA wal_autocheckpoint=1000")  # P2: explicit checkpoint interval

        self._init_schema()

        # P2 fix: only run recover() once per DB path per process
        path_key = str(self._db_path.resolve())
        if path_key not in State._initialized_paths:
            State._initialized_paths.add(path_key)
            self.recover()

    # ── Schema ────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        current_version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version >= _SCHEMA_VERSION:
            return

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_items (
                idem_key    TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id   TEXT NOT NULL,
                url         TEXT NOT NULL,
                status      TEXT NOT NULL,
                output_path TEXT,
                error       TEXT,
                attempts    INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_processed_status
                ON processed_items(status);
            CREATE INDEX IF NOT EXISTS idx_processed_source
                ON processed_items(source_type, source_id);

            CREATE TABLE IF NOT EXISTS feed_cursors (
                source_type  TEXT NOT NULL,
                account      TEXT NOT NULL,
                last_seen_id TEXT,
                last_seen_at TEXT,
                PRIMARY KEY (source_type, account)
            );

            CREATE TABLE IF NOT EXISTS delivery_log (
                digest_id    TEXT PRIMARY KEY,
                channel      TEXT NOT NULL,
                status       TEXT NOT NULL,
                response     TEXT,
                delivered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS batch_runs (
                run_id      TEXT PRIMARY KEY,
                user_url    TEXT NOT NULL,
                total       INTEGER NOT NULL,
                completed   INTEGER DEFAULT 0,
                failed      INTEGER DEFAULT 0,
                state       TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS batch_items (
                run_id      TEXT NOT NULL REFERENCES batch_runs(run_id),
                item_id     TEXT NOT NULL,
                status      TEXT NOT NULL,
                attempts    INTEGER DEFAULT 0,
                output_path TEXT,
                error       TEXT,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (run_id, item_id)
            );

            PRAGMA user_version = %d;
        """ % _SCHEMA_VERSION)

    # ── Advisory lock ─────────────────────────────────────────────────

    @contextmanager
    def _lock(self):
        """File-based advisory lock to prevent concurrent state mutations."""
        import sys

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(self._lock_path, "w")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    # ── Idempotency ───────────────────────────────────────────────────

    def is_processed(self, idem_key: str) -> bool:
        """Check if an item has already been processed (any status)."""
        row = self._conn.execute(
            "SELECT 1 FROM processed_items WHERE idem_key = ?", (idem_key,)
        ).fetchone()
        return row is not None

    def get_item(self, idem_key: str) -> Optional[Item]:
        """Get full item details by idempotent key."""
        row = self._conn.execute(
            "SELECT * FROM processed_items WHERE idem_key = ?", (idem_key,)
        ).fetchone()
        if row is None:
            return None
        return Item(**dict(row))

    def mark_processed(
        self,
        idem_key: str,
        source_type: str,
        source_id: str,
        url: str,
        status: str,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Insert or update a processed item. Returns True if actually inserted (not duplicate)."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")

        now = _utcnow_str()
        with self._lock():
            # P1 fix: Use INSERT OR IGNORE + separate UPDATE to avoid TOCTOU.
            # INSERT OR IGNORE returns silently if key exists (no update).
            # Callers check the return value to know if this was a new item.
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO processed_items
                    (idem_key, source_type, source_id, url, status,
                     output_path, error, attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (idem_key, source_type, source_id, url, status,
                 output_path, error, now, now),
            )
            inserted = cur.rowcount > 0
            if not inserted:
                # Already exists — update status/output/error
                self._conn.execute(
                    """
                    UPDATE processed_items
                    SET status = ?, output_path = COALESCE(?, output_path),
                        error = ?, updated_at = ?
                    WHERE idem_key = ?
                    """,
                    (status, output_path, error, now, idem_key),
                )
            return inserted

    # ── State machine ─────────────────────────────────────────────────

    def transition(
        self,
        idem_key: str,
        to_status: str,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Transition an item to a new status with validation.

        Raises ValueError if the transition is not allowed.
        Increments attempts on failure transitions.
        """
        if to_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {to_status}")

        with self._lock():
            row = self._conn.execute(
                "SELECT status, attempts FROM processed_items WHERE idem_key = ?",
                (idem_key,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Item not found: {idem_key}")

            current_status = row["status"]
            attempts = row["attempts"]

            if to_status not in VALID_TRANSITIONS.get(current_status, set()):
                raise ValueError(
                    f"Invalid transition: {current_status} → {to_status}. "
                    f"Allowed: {VALID_TRANSITIONS.get(current_status, set())}"
                )

            # Increment attempts on failure
            new_attempts = attempts
            if to_status == "failed":
                new_attempts = attempts + 1
                if new_attempts >= MAX_ATTEMPTS:
                    to_status = "permanently_failed"

            now = _utcnow_str()
            self._conn.execute(
                """
                UPDATE processed_items
                SET status = ?, output_path = COALESCE(?, output_path),
                    error = ?, attempts = ?, updated_at = ?
                WHERE idem_key = ?
                """,
                (to_status, output_path, error, new_attempts, now, idem_key),
            )

    def get_recoverable(self, stale_after_sec: int = STALE_THRESHOLD_SEC) -> list[Item]:
        """Find items stuck in non-terminal states beyond the stale threshold."""
        cutoff = (_utcnow() - timedelta(seconds=stale_after_sec)).isoformat()
        rows = self._conn.execute(
            """
            SELECT * FROM processed_items
            WHERE status NOT IN ('done', 'permanently_failed', 'pending', 'failed')
              AND updated_at < ?
            """,
            (cutoff,),
        ).fetchall()
        return [Item(**dict(r)) for r in rows]

    def recover(self) -> int:
        """Reset stale items back to pending. Returns count of recovered items.

        P1 fix: Wrapped in _lock() + explicit transaction to prevent partial recovery.
        """
        now = _utcnow_str()
        with self._lock():
            stale = self.get_recoverable()
            if not stale:
                return 0
            with self._conn:  # explicit BEGIN...COMMIT
                for item in stale:
                    self._conn.execute(
                        "UPDATE processed_items SET status = 'pending', updated_at = ? WHERE idem_key = ?",
                        (now, item.idem_key),
                    )
            return len(stale)

    def get_retryable(self) -> list[Item]:
        """Find failed items whose backoff period has elapsed."""
        now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT * FROM processed_items WHERE status = 'failed'"
        ).fetchall()
        retryable = []
        for row in rows:
            item = Item(**dict(row))
            updated = datetime.fromisoformat(item.updated_at)
            backoff = BACKOFF_INTERVALS[min(item.attempts - 1, len(BACKOFF_INTERVALS) - 1)]
            if (now - updated).total_seconds() >= backoff:
                retryable.append(item)
        return retryable

    # ── Feed cursors ──────────────────────────────────────────────────

    def get_cursor(self, source_type: str, account: str) -> Optional[Cursor]:
        row = self._conn.execute(
            "SELECT * FROM feed_cursors WHERE source_type = ? AND account = ?",
            (source_type, account),
        ).fetchone()
        if row is None:
            return None
        return Cursor(**dict(row))

    def update_cursor(
        self,
        source_type: str,
        account: str,
        last_seen_id: str,
        last_seen_at: Optional[datetime] = None,
    ) -> None:
        """Update feed cursor. P1 fix: only advances, never regresses.

        If another worker already updated to a higher ID, this call is a no-op.
        Prevents the race where worker A(id=100) finishes after worker B(id=200)
        and regresses the cursor back to 100.
        """
        now = (last_seen_at or datetime.now(timezone.utc)).isoformat()
        with self._lock():
            # P1 fix: use CAST for numeric comparison to handle Twitter snowflake IDs
            self._conn.execute(
                """
                INSERT INTO feed_cursors (source_type, account, last_seen_id, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_type, account) DO UPDATE SET
                    last_seen_id = excluded.last_seen_id,
                    last_seen_at = excluded.last_seen_at
                WHERE feed_cursors.last_seen_id IS NULL
                   OR CAST(feed_cursors.last_seen_id AS INTEGER) < CAST(excluded.last_seen_id AS INTEGER)
                   OR (feed_cursors.last_seen_id < excluded.last_seen_id
                       AND feed_cursors.last_seen_id NOT GLOB '[0-9]*')
                """,
                (source_type, account, last_seen_id, now),
            )

    # ── Delivery log ──────────────────────────────────────────────────

    def record_delivery(
        self,
        digest_id: str,
        channel: str,
        status: str,
        response: Optional[str] = None,
    ) -> None:
        now = _utcnow_str()
        with self._lock():
            self._conn.execute(
                """
                INSERT INTO delivery_log (digest_id, channel, status, response, delivered_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(digest_id) DO UPDATE SET
                    status = excluded.status,
                    response = excluded.response,
                    delivered_at = excluded.delivered_at
                """,
                (digest_id, channel, status, response, now),
            )

    def was_delivered(self, digest_id: str, channel: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM delivery_log WHERE digest_id = ? AND channel = ? AND status = 'success'",
            (digest_id, channel),
        ).fetchone()
        return row is not None

    @staticmethod
    def make_digest_id(content: str, sources: list[str], time_window: str) -> str:
        """Compute deterministic digest ID from content + metadata."""
        payload = json.dumps(
            {"content": content, "sources": sorted(sources), "window": time_window},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ── Batch runs ────────────────────────────────────────────────────

    def start_batch(self, user_url: str, items: list[str]) -> str:
        """Create a new batch run. Returns run_id."""
        run_id = uuid.uuid4().hex[:12]
        now = _utcnow_str()
        with self._lock():
            with self._conn:  # explicit transaction
                self._conn.execute(
                    "INSERT INTO batch_runs (run_id, user_url, total, state, started_at) VALUES (?, ?, ?, 'running', ?)",
                    (run_id, user_url, len(items), now),
                )
                for item_id in items:
                    self._conn.execute(
                        "INSERT INTO batch_items (run_id, item_id, status, updated_at) VALUES (?, ?, 'pending', ?)",
                        (run_id, item_id, now),
                    )
        return run_id

    def update_batch_item(
        self,
        run_id: str,
        item_id: str,
        status: str,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid batch item status: {status}")
        now = _utcnow_str()
        with self._lock():
            self._conn.execute(
                """
                UPDATE batch_items
                SET status = ?, output_path = COALESCE(?, output_path),
                    error = ?, attempts = attempts + 1, updated_at = ?
                WHERE run_id = ? AND item_id = ?
                """,
                (status, output_path, error, now, run_id, item_id),
            )
            # Update run counters
            if status == "done":
                self._conn.execute(
                    "UPDATE batch_runs SET completed = completed + 1 WHERE run_id = ?",
                    (run_id,),
                )
            elif status in ("failed", "permanently_failed"):
                self._conn.execute(
                    "UPDATE batch_runs SET failed = failed + 1 WHERE run_id = ?",
                    (run_id,),
                )

    def finish_batch(self, run_id: str, state: str) -> None:
        now = _utcnow_str()
        with self._lock():
            self._conn.execute(
                "UPDATE batch_runs SET state = ?, finished_at = ? WHERE run_id = ?",
                (state, now, run_id),
            )

    def get_batch_run(self, run_id: str) -> Optional[BatchRun]:
        row = self._conn.execute(
            "SELECT * FROM batch_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return BatchRun(**dict(row))

    # ── Inspection (for CLI debug) ────────────────────────────────────

    def inspect(self, idem_key: str) -> Optional[dict]:
        """Return full item details as dict for CLI inspection."""
        item = self.get_item(idem_key)
        if item is None:
            return None
        return {
            "idem_key": item.idem_key,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "url": item.url,
            "status": item.status,
            "output_path": item.output_path,
            "error": item.error,
            "attempts": item.attempts,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def stats(self) -> dict:
        """Return aggregate stats for CLI status display."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM processed_items GROUP BY status"
        ).fetchall()
        by_status = {row["status"]: row["cnt"] for row in rows}

        cursor_count = self._conn.execute("SELECT COUNT(*) FROM feed_cursors").fetchone()[0]
        delivery_count = self._conn.execute("SELECT COUNT(*) FROM delivery_log").fetchone()[0]
        batch_count = self._conn.execute("SELECT COUNT(*) FROM batch_runs").fetchone()[0]

        return {
            "items": by_status,
            "total_items": sum(by_status.values()),
            "cursors": cursor_count,
            "deliveries": delivery_count,
            "batch_runs": batch_count,
            "db_path": str(self._db_path),
            "db_size_mb": round(self._db_path.stat().st_size / 1024 / 1024, 2)
            if self._db_path.exists()
            else 0,
        }

    # ── Cleanup ───────────────────────────────────────────────────────

    def cleanup(self, max_age_days: int = 14, vacuum: bool = True) -> int:
        """Delete processed items and delivery logs older than max_age_days.

        P2 fix: Optionally VACUUM after cleanup to reclaim disk space.
        """
        cutoff = (_utcnow() - timedelta(days=max_age_days)).isoformat()
        with self._lock():
            cur1 = self._conn.execute(
                "DELETE FROM processed_items WHERE status IN ('done', 'permanently_failed') AND updated_at < ?",
                (cutoff,),
            )
            cur2 = self._conn.execute(
                "DELETE FROM delivery_log WHERE delivered_at < ?", (cutoff,)
            )
            removed = cur1.rowcount + cur2.rowcount
            if vacuum and removed > 0:
                self._conn.execute("VACUUM")
        return removed

    # ── Context manager ───────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ── Helpers ───────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    """Current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _utcnow_str() -> str:
    """Current UTC time as ISO 8601 string."""
    return _utcnow().isoformat()
