"""Performance profiling, parallel execution, and download caching."""
from __future__ import annotations

import asyncio
import functools
import json
import pickle  # noqa: S403 — needed for ProcessPoolExecutor compatibility checks
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

T = TypeVar("T")
R = TypeVar("R")

# ---------------------------------------------------------------------------
# Global step timings — keyed by step name, values are lists of durations
# ---------------------------------------------------------------------------
STEP_TIMES: Dict[str, List[float]] = {}
_STEP_TIMES_LOCK = threading.Lock()
_MAX_TIMESTEPS = 1000  # P1 fix: cap per-step list size


# ---------------------------------------------------------------------------
# @profile_step decorator
# ---------------------------------------------------------------------------

def profile_step(fn: Callable[..., Any] | None = None, *, name: str | None = None) -> Any:
    """Decorator that records execution time in ``STEP_TIMES``.

    Works for both sync and async functions.  The recorded key defaults to the
    function's ``__name__`` but can be overridden with *name*.
    """

    def _decorator(func: Callable[..., Any]) -> Any:
        step_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - t0
                    with _STEP_TIMES_LOCK:
                        times = STEP_TIMES.setdefault(step_name, [])
                        times.append(elapsed)
                        if len(times) > _MAX_TIMESTEPS:
                            STEP_TIMES[step_name] = times[-_MAX_TIMESTEPS:]
            return _async_wrapper
        else:
            @functools.wraps(func)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - t0
                    with _STEP_TIMES_LOCK:
                        times = STEP_TIMES.setdefault(step_name, [])
                        times.append(elapsed)
                        if len(times) > _MAX_TIMESTEPS:
                            STEP_TIMES[step_name] = times[-_MAX_TIMESTEPS:]
            return _sync_wrapper

    if fn is not None:
        return _decorator(fn)
    return _decorator


# ---------------------------------------------------------------------------
# PerformanceReport
# ---------------------------------------------------------------------------

class PerformanceReport:
    """Aggregates ``STEP_TIMES`` into count/total/mean/min/max stats."""

    def __init__(self, times: Dict[str, List[float]] | None = None):
        self._times = times if times is not None else STEP_TIMES

    def aggregate(self) -> Dict[str, Dict[str, float]]:
        """Return per-step aggregated stats."""
        result: Dict[str, Dict[str, float]] = {}
        for step, durations in self._times.items():
            result[step] = {
                "count": len(durations),
                "total": sum(durations),
                "mean": sum(durations) / len(durations) if durations else 0.0,
                "min": min(durations) if durations else 0.0,
                "max": max(durations) if durations else 0.0,
            }
        return result

    def to_json(self, indent: int = 2) -> str:
        """Return aggregated stats as a JSON string."""
        data = self.aggregate()
        return json.dumps(data, indent=indent)

    def to_markdown(self) -> str:
        """Return a Markdown table of aggregated stats."""
        data = self.aggregate()
        if not data:
            return ""
        lines = ["| Step | Count | Total (s) | Mean (s) | Min (s) | Max (s) |",
                 "|------|-------|-----------|----------|---------|---------|"]
        for step, stats in data.items():
            lines.append(
                f"| {step} | {stats['count']} "
                f"| {stats['total']:.4f} | {stats['mean']:.4f} "
                f"| {stats['min']:.4f} | {stats['max']:.4f} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# _verify_picklable
# ---------------------------------------------------------------------------

def _verify_picklable(item: Any) -> None:
    """Raise ``TypeError`` if *item* cannot be pickled (needed for ProcessPool)."""
    try:
        pickle.dumps(item)
    except (pickle.PicklingError, TypeError) as exc:
        raise TypeError(f"Item is not picklable: {exc}") from exc


# ---------------------------------------------------------------------------
# parallel_map  (sync)
# ---------------------------------------------------------------------------

def parallel_map(
    fn: Callable[[T], R],
    items: List[T],
    *,
    mode: str = "thread",
    max_workers: Optional[int] = None,
    chunk_size: int = 1,
) -> List[R]:
    """Map *fn* over *items* using a thread or process pool.

    Parameters
    ----------
    mode : ``"thread"`` or ``"process"``
    max_workers : pool size (default: ``min(32, os.cpu_count() + 4)``)
    chunk_size : passed to ``ProcessPoolExecutor.map`` (ignored for threads)
    """
    if mode == "process":
        for item in items:
            _verify_picklable(item)
        executor_cls = ProcessPoolExecutor
    else:
        executor_cls = ThreadPoolExecutor

    with executor_cls(max_workers=max_workers) as pool:
        return list(pool.map(fn, items, chunksize=chunk_size))


# ---------------------------------------------------------------------------
# parallel_map_async  (async, batch submission)
# ---------------------------------------------------------------------------

async def parallel_map_async(
    fn: Callable[[T], Any],
    items: List[T],
    *,
    mode: str = "thread",
    max_workers: Optional[int] = None,
    batch_size: int = 10,
) -> List[Any]:
    """Async version — submits items in batches via ``asyncio.gather``.

    For async *fn*, coroutines are gathered directly.  For sync *fn*, each call
    runs in an executor.  Batches keep memory bounded.
    """
    is_async = asyncio.iscoroutinefunction(fn)

    if not is_async:
        loop = asyncio.get_running_loop()

    if mode == "process":
        for item in items:
            _verify_picklable(item)

    executor = None
    if not is_async:
        executor = ThreadPoolExecutor(max_workers=max_workers) if mode == "thread" else ProcessPoolExecutor(max_workers=max_workers)

    try:
        results: List[Any] = []
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            if is_async:
                coros = [fn(item) for item in batch]
            else:
                coros = [loop.run_in_executor(executor, fn, item) for item in batch]
            results.extend(await asyncio.gather(*coros))
        return results
    finally:
        if executor is not None:
            executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# parallel_map_async_safe  (async, per-item error handling)
# ---------------------------------------------------------------------------

async def parallel_map_async_safe(
    fn: Callable[[T], Any],
    items: List[T],
    *,
    mode: str = "thread",
    max_workers: Optional[int] = None,
    batch_size: int = 10,
) -> Tuple[List[Any], List[Exception]]:
    """Like ``parallel_map_async`` but captures per-item errors.

    Returns ``(results, errors)`` where *results* contains only successful
    values and *errors* contains the exceptions from failed items.
    """
    is_async = asyncio.iscoroutinefunction(fn)

    if not is_async:
        loop = asyncio.get_running_loop()

    if mode == "process":
        for item in items:
            _verify_picklable(item)

    executor = None
    if not is_async:
        executor = ThreadPoolExecutor(max_workers=max_workers) if mode == "thread" else ProcessPoolExecutor(max_workers=max_workers)

    try:
        results: List[Any] = []
        errors: List[Exception] = []
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            if is_async:
                coros = [fn(item) for item in batch]
            else:
                coros = [loop.run_in_executor(executor, fn, item) for item in batch]
            outcomes = await asyncio.gather(*coros, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    errors.append(outcome)
                else:
                    results.append(outcome)
        return results, errors
    finally:
        if executor is not None:
            executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# DownloadCache
# ---------------------------------------------------------------------------

class DownloadCache:
    """In-memory URL-to-path dedup cache."""

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}

    def get(self, url: str) -> Optional[str]:
        """Return cached path for *url*, or ``None``."""
        return self._cache.get(url)

    def put(self, url: str, path: str) -> None:
        """Cache *path* for *url* (no-op if already cached)."""
        if url not in self._cache:
            self._cache[url] = path

    def seen(self, url: str) -> bool:
        """Return ``True`` if *url* has been cached."""
        return url in self._cache
