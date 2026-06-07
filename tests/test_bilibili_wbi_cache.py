"""Tests for WBI key TTL cache in shared_utils.

Covers:
1. Cache miss → fetch + store; second call within TTL → reuse
2. TTL expiry → re-fetch
3. Invalidation on -6 (signature error)
4. Concurrent refresh serializes (only 1 fetch under N threads)
5. Log sanitization (WBI key never appears in log output)
"""

from __future__ import annotations

import io
import logging
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from builderpulse.core import shared_utils
from builderpulse.core.shared_utils import (
    WBI_CACHE_TTL_SECONDS,
    get_wbi_key,
    invalidate_wbi_cache,
)


@pytest.fixture(autouse=True)
def reset_wbi_cache():
    """Reset module-level WBI cache state before and after each test."""
    shared_utils._wbi_cache["key"] = None
    shared_utils._wbi_cache["fetched_at"] = 0.0
    yield
    shared_utils._wbi_cache["key"] = None
    shared_utils._wbi_cache["fetched_at"] = 0.0


# -- 1. cache miss → fetch + store; second call within TTL → reuse --


def test_cache_miss_fetches_and_stores():
    """First call fetches; second call within TTL reuses cache (1 fetch total)."""
    client = MagicMock(name="client")
    with patch.object(
        shared_utils,
        "_fetch_wbi_key_from_bilibili",
        return_value="key_abc",
    ) as mock_fetch:
        k1 = get_wbi_key(client)
        k2 = get_wbi_key(client)

    assert k1 == "key_abc"
    assert k2 == "key_abc"
    assert mock_fetch.call_count == 1


# -- 2. TTL expiry → re-fetch --


def test_cache_ttl_expiry():
    """Cache older than TTL is stale; next call re-fetches."""
    client = MagicMock(name="client")
    with patch.object(
        shared_utils,
        "_fetch_wbi_key_from_bilibili",
        side_effect=["key_v1", "key_v2"],
    ) as mock_fetch:
        # First call populates the cache
        k1 = get_wbi_key(client)
        assert k1 == "key_v1"
        assert mock_fetch.call_count == 1

        # Simulate 31 minutes passing by rewinding fetched_at
        shared_utils._wbi_cache["fetched_at"] = time.time() - (31 * 60)

        # Second call sees stale cache → re-fetches
        k2 = get_wbi_key(client)

    assert k2 == "key_v2"
    assert mock_fetch.call_count == 2


# -- 3. invalidation on -6 (signature error) --


def test_cache_invalidation_on_minus_six():
    """invalidate_wbi_cache() clears the cache (call site handles -6 by invoking it)."""
    shared_utils._wbi_cache["key"] = "key_v1"
    shared_utils._wbi_cache["fetched_at"] = time.time()
    assert shared_utils._wbi_cache["key"] == "key_v1"

    invalidate_wbi_cache()

    assert shared_utils._wbi_cache["key"] is None
    assert shared_utils._wbi_cache["fetched_at"] == 0.0


# -- 4. concurrent refresh serializes (only 1 fetch under N threads) --


def test_concurrent_refresh_serializes():
    """10 concurrent threads → only 1 fetch (others wait on lock and read cache)."""
    call_count = 0
    call_lock = threading.Lock()
    barrier = threading.Barrier(10)

    def slow_fetch(client):
        nonlocal call_count
        with call_lock:
            call_count += 1
        # Sleep simulates Bilibili nav API latency; concurrent threads should
        # all see the cache populated by the first arriver, not trigger their own fetch.
        time.sleep(0.05)
        return "key_abc"

    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()  # synchronize start so all 10 threads contend at once
        with results_lock:
            results.append(get_wbi_key(MagicMock(name="client")))

    with patch.object(
        shared_utils, "_fetch_wbi_key_from_bilibili", side_effect=slow_fetch
    ):
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert all(r == "key_abc" for r in results), f"Got mixed results: {results}"
    assert len(results) == 10
    assert call_count == 1, f"Expected 1 fetch, got {call_count}"


# -- 5. log sanitization --


def test_log_sanitization():
    """WBI key value must never appear in log output."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    test_logger = logging.getLogger("builderpulse.core.shared_utils")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    # Disable propagation to avoid noise from the global SensitiveDataFilter
    # double-redaction (the test checks "any log line" emitted by our logger).
    previous_propagate = test_logger.propagate
    test_logger.propagate = False

    try:
        client = MagicMock(name="client")
        with patch.object(
            shared_utils,
            "_fetch_wbi_key_from_bilibili",
            return_value="SECRET_KEY_xyz",
        ):
            # First call: cache miss → fetch happens
            get_wbi_key(client)
            # Second call: cache hit
            get_wbi_key(client)
            # Invalidation (which also logs at DEBUG)
            invalidate_wbi_cache()
        output = log_stream.getvalue()
    finally:
        test_logger.removeHandler(handler)
        test_logger.propagate = previous_propagate

    assert "SECRET_KEY_xyz" not in output, (
        f"WBI key leaked into log output:\n{output}"
    )


# -- sanity check on the TTL constant --


def test_wbi_cache_ttl_is_30_minutes():
    """WBI_CACHE_TTL_SECONDS == 30*60 per v2.0.1 design spec."""
    assert WBI_CACHE_TTL_SECONDS == 30 * 60
