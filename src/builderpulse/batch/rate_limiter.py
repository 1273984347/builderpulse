"""Token-bucket rate limiter using ``asyncio.Lock``.

The bucket refills at ``qps`` tokens per second (up to ``qps`` capacity).
``acquire()`` waits asynchronously until a token is available.
"""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Async token-bucket rate limiter.

    Args:
        qps: Queries (requests) per second — also the bucket capacity.
        tokens: Initial token count.  Defaults to *qps* (full bucket).
    """

    def __init__(self, qps: float = 10.0, tokens: float | None = None) -> None:
        self.qps = qps
        self._tokens = tokens if tokens is not None else qps
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # How long until 1 token is available
                wait = (1.0 - self._tokens) / self.qps

            # Sleep outside the lock
            await asyncio.sleep(wait)

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self.qps, self._tokens + elapsed * self.qps)
