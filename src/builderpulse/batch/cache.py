"""SQLite-backed batch result cache with thread-local connections.

WAL mode + ``synchronous=NORMAL`` for performance.  Each thread gets its
own connection via ``threading.local()`` so no ``check_same_thread=False``
is needed.

.. note::

    Each thread that uses the cache **must** call :meth:`close` (or use the
    context-manager) before exiting — otherwise the thread-local SQLite
    connection will leak.  If multiple threads share a ``BatchCache`` instance,
    each thread should call ``cache.close()`` (or ``cache.close_thread()``
    which is an alias) before the thread exits.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── BatchCache ──────────────────────────────────────────────────────────


class BatchCache:
    """SQLite cache keyed by SHA256(url).

    Usage::

        with BatchCache(path) as cache:
            cache.set(url, "done", result={"title": "..."})
            row = cache.get(url)

    **Important:** Each thread that uses the cache must call :meth:`close`
    (or use the context manager) before exiting to avoid leaking connections.
    """

    # Track all instances for close_all() — weak refs avoid preventing GC
    _instances: List["weakref.ref[BatchCache]"] = []
    _instances_lock = threading.Lock()

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

        with BatchCache._instances_lock:
            BatchCache._instances.append(weakref.ref(self))

    # ── Schema ────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache (
                url_hash    TEXT PRIMARY KEY,
                status      TEXT NOT NULL,
                result      TEXT,
                error_code  TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
        """)

    def _get_conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), isolation_level=None)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ── Hashing ───────────────────────────────────────────────────────

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    # ── CRUD ──────────────────────────────────────────────────────────

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Lookup by SHA256(url). Returns dict or None."""
        row = self._get_conn().execute(
            "SELECT * FROM cache WHERE url_hash = ?",
            (self._hash_url(url),),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("result"):
            d["result"] = json.loads(d["result"])
        return d

    def set(
        self,
        url: str,
        status: str,
        result: Any = None,
        error_code: Optional[str] = None,
    ) -> None:
        """Upsert with ON CONFLICT."""
        now = datetime.now(timezone.utc).isoformat()
        result_json = json.dumps(result) if result is not None else None
        self._get_conn().execute(
            """
            INSERT INTO cache (url_hash, status, result, error_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                status = excluded.status,
                result = excluded.result,
                error_code = excluded.error_code,
                updated_at = excluded.updated_at
            """,
            (self._hash_url(url), status, result_json, error_code, now, now),
        )

    def cleanup(self, max_age_days: int = 7) -> int:
        """Remove entries older than *max_age_days*.  Returns count removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        cur = self._get_conn().execute(
            "DELETE FROM cache WHERE created_at < ?", (cutoff,)
        )
        removed = cur.rowcount

        # Orphan WAL file cleanup: checkpoint to merge WAL into main DB
        try:
            self._get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass  # another writer holds the WAL — best-effort

        return removed

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the thread-local connection for the calling thread.

        Each thread that uses the cache must call this method (or use the
        context manager) before exiting.
        """
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def close_thread(self) -> None:
        """Alias for :meth:`close`. Use when multiple threads share a cache."""
        self.close()

    @classmethod
    def close_all(cls) -> None:
        """Close all BatchCache instances (for test cleanup)."""
        with cls._instances_lock:
            for ref in cls._instances:
                inst = ref()
                if inst is not None:
                    inst.close()
            cls._instances.clear()

    # ── Context manager ───────────────────────────────────────────────

    def __del__(self) -> None:
        """Safety net: close thread-local connection on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "BatchCache":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
