"""Tests for builderpulse.batch.rate_limiter — RateLimiter."""
from __future__ import annotations

import asyncio
import time

import pytest

from builderpulse.batch.rate_limiter import RateLimiter


class TestRateLimiterAcquire:
    """Token bucket acquire() behavior."""

    @pytest.mark.asyncio
    async def test_acquire_consumes_token(self) -> None:
        limiter = RateLimiter(qps=10)
        await limiter.acquire()
        # After one acquire, tokens should be reduced
        assert limiter._tokens < 10

    @pytest.mark.asyncio
    async def test_acquire_waits_when_empty(self) -> None:
        limiter = RateLimiter(qps=1, tokens=1)
        # Exhaust the single token
        await limiter.acquire()
        # Next acquire should block briefly then succeed
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have waited roughly 1 second (1/qps)
        assert elapsed >= 0.5  # generous margin for CI

    @pytest.mark.asyncio
    async def test_acquire_respects_qps(self) -> None:
        limiter = RateLimiter(qps=100)
        # Should be able to acquire several quickly
        for _ in range(5):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self) -> None:
        limiter = RateLimiter(qps=100, tokens=1)
        await limiter.acquire()
        # Wait a bit for refill
        await asyncio.sleep(0.05)
        # Should be able to acquire again without long wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
