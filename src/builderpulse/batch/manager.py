"""BatchManager — orchestrates batch download → transcribe → summarize.

Composes :class:`BatchCache`, :class:`DiskGuard`, :class:`RateLimiter`,
and an ``asyncio.Semaphore`` for concurrency control.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from builderpulse.batch.cache import BatchCache
from builderpulse.batch.disk_guard import DiskFullError, DiskGuard
from builderpulse.batch.rate_limiter import RateLimiter
from builderpulse.batch.retry import RetryExhausted
from builderpulse.core.config import Config
from builderpulse.core.error_codes import ErrorCode
from builderpulse.core.models import SourceRef

logger = logging.getLogger("builderpulse.batch")


class BatchManager:
    """Orchestrates batch processing of multiple URLs.

    Args:
        config: BuilderPulse Config (or None for defaults).
        db_path: Path to the SQLite cache database.
        concurrency: Max concurrent items.
        qps: Requests per second rate limit.
        min_disk_bytes: Minimum free disk bytes.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        db_path: Path | str = Path("batch_cache.db"),
        concurrency: int = 5,
        qps: float = 5.0,
        min_disk_bytes: int = 500 * 1024 * 1024,
    ) -> None:
        self._config = config
        self._cache = BatchCache(db_path)
        self._disk = DiskGuard(min_bytes=min_disk_bytes)
        # P1 fix: store params; create asyncio primitives lazily in process_batch_async
        self._concurrency = concurrency
        self._qps = qps

    # ── Public API ────────────────────────────────────────────────────

    def process_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Process a list of URLs synchronously.  Returns list of result dicts.

        Note: This sync path is intentionally sequential with no rate limiting.
        Rate limiting is only needed for async/concurrent paths to avoid
        overwhelming external services. Sequential processing is inherently
        self-throttling.
        """
        results: List[Dict[str, Any]] = []
        for url in urls:
            try:
                result = self._process_item(url)
                results.append(result)
            except Exception as exc:
                error_code = self._classify_error(exc)
                results.append({
                    "url": url,
                    "status": "failed",
                    "error_code": error_code,
                    "error": str(exc),
                })
        return results

    async def process_batch_async(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Process URLs concurrently with semaphore + rate limiter."""
        # P1 fix: create asyncio primitives lazily (no event loop in __init__)
        sem = asyncio.Semaphore(self._concurrency)
        limiter = RateLimiter(qps=self._qps)

        async def _guarded(url: str) -> Dict[str, Any]:
            async with sem:
                await limiter.acquire()
                # P2 fix: prefer get_running_loop() — get_event_loop() is
                # deprecated for use inside coroutines (DeprecationWarning
                # since Python 3.10). Fall back only if somehow no loop is
                # running, which would itself be a programming error here.
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    import warnings
                    warnings.warn(
                        "No running event loop; falling back to "
                        "asyncio.get_event_loop() (deprecated)",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._process_item, url)

        tasks = [_guarded(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: List[Dict[str, Any]] = []
        for url, res in zip(urls, results):
            if isinstance(res, Exception):
                error_code = self._classify_error(res)
                out.append({
                    "url": url,
                    "status": "failed",
                    "error_code": error_code,
                    "error": str(res),
                })
            else:
                out.append(res)
        return out

    # ── Internal ──────────────────────────────────────────────────────

    def _process_item(self, url: str) -> Dict[str, Any]:
        """Single-item pipeline: cache → disk → download → transcribe → summarize → cache."""
        # 1. Cache hit?
        cached = self._cache.get(url)
        if cached and cached.get("status") == "done":
            return cached

        # 2. Disk space check
        workspace = self._config.workspace if self._config else str(Path.home() / ".builderpulse" / "output")
        self._disk.check(workspace)

        # 3. Download → transcribe → summarize via pipeline
        source = SourceRef.from_url(url)

        from builderpulse.core.pipeline import (
            Pipeline,
            step_download,
            step_transcribe,
            step_summarize,
        )

        p = Pipeline(config=self._config)
        p.add(step_download)
        p.add(step_transcribe)
        p.add(step_summarize)
        ctx = p.run(source)

        if ctx.error:
            self._cache.set(url, "failed", error_code=ErrorCode.BATCH_ITEM_FAILED)
            return {"url": url, "status": "failed", "error": ctx.error}

        result: Dict[str, Any] = {
            "url": url,
            "status": "done",
            "title": source.native_id,
        }
        if ctx.transcript:
            result["word_count"] = ctx.transcript.word_count
        if ctx.summary:
            result["summary"] = ctx.summary[:500]

        self._cache.set(url, "done", result=result)
        return result

    # ── Error classification ──────────────────────────────────────────

    @staticmethod
    def _classify_error(exc: BaseException) -> str:
        """Map exception types to ErrorCode values.

        Walks ``__cause__`` chain to find the root cause.
        """
        # Walk cause chain
        chain: list[BaseException] = []
        current: BaseException | None = exc
        while current is not None:
            chain.append(current)
            current = current.__cause__

        for e in chain:
            if isinstance(e, DiskFullError):
                return ErrorCode.BATCH_DISK_FULL
            if isinstance(e, PermissionError):
                return ErrorCode.DOWNLOAD_FORBIDDEN

        # RetryExhausted: inspect history for root cause type
        if isinstance(exc, RetryExhausted):
            for _, inner, _ in exc.history:
                if isinstance(inner, ConnectionError):
                    return ErrorCode.BATCH_ITEM_FAILED
                if isinstance(inner, TimeoutError):
                    return ErrorCode.BATCH_ITEM_FAILED

        return ErrorCode.BATCH_ITEM_FAILED

    # ── Lifecycle ─────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Close cache and release resources."""
        self._cache.close()
