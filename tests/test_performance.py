"""Tests for builderpulse.infra.performance."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from builderpulse.infra.performance import (
    DownloadCache,
    PerformanceReport,
    STEP_TIMES,
    _verify_picklable,
    parallel_map,
    parallel_map_async,
    parallel_map_async_safe,
    profile_step,
)


# ---------------------------------------------------------------------------
# profile_step
# ---------------------------------------------------------------------------

class TestProfileStep:
    def teardown_method(self):
        STEP_TIMES.clear()

    def test_records_execution_time(self):
        @profile_step
        def slow():
            time.sleep(0.05)

        slow()
        assert "slow" in STEP_TIMES
        assert len(STEP_TIMES["slow"]) == 1
        assert STEP_TIMES["slow"][0] >= 0.04

    def test_records_multiple_calls(self):
        @profile_step
        def fast():
            return 42

        fast()
        fast()
        assert len(STEP_TIMES["fast"]) == 2

    def test_preserves_return_value(self):
        @profile_step
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_custom_name(self):
        @profile_step(name="custom")
        def fn():
            pass

        fn()
        assert "custom" in STEP_TIMES

    def test_async_function(self):
        @profile_step
        async def async_work():
            await asyncio.sleep(0.02)
            return "done"

        result = asyncio.run(async_work())
        assert result == "done"
        assert "async_work" in STEP_TIMES
        assert STEP_TIMES["async_work"][0] >= 0.01


# ---------------------------------------------------------------------------
# PerformanceReport
# ---------------------------------------------------------------------------

class TestPerformanceReport:
    def setup_method(self):
        STEP_TIMES.clear()

    def test_empty_report(self):
        report = PerformanceReport()
        assert report.to_json() == "{}"

    def test_aggregate_single_step(self):
        STEP_TIMES["step1"] = [0.1, 0.2, 0.3]
        report = PerformanceReport()
        data = report.aggregate()
        assert data["step1"]["count"] == 3
        assert abs(data["step1"]["total"] - 0.6) < 1e-9
        assert abs(data["step1"]["mean"] - 0.2) < 1e-9
        assert abs(data["step1"]["min"] - 0.1) < 1e-9
        assert abs(data["step1"]["max"] - 0.3) < 1e-9

    def test_to_json_format(self):
        STEP_TIMES["x"] = [1.0]
        report = PerformanceReport()
        j = report.to_json()
        assert '"count": 1' in j
        assert '"total"' in j

    def test_to_markdown_table(self):
        STEP_TIMES["a"] = [0.5]
        STEP_TIMES["b"] = [1.0]
        report = PerformanceReport()
        md = report.to_markdown()
        assert "| Step |" in md
        assert "a" in md
        assert "b" in md


# ---------------------------------------------------------------------------
# parallel_map
# ---------------------------------------------------------------------------

def _inc(x):
    return x + 1


class TestParallelMap:
    def test_thread_mode(self):
        result = parallel_map(lambda x: x * 2, [1, 2, 3], mode="thread")
        assert sorted(result) == [2, 4, 6]

    def test_process_mode(self):
        result = parallel_map(_inc, [10, 20], mode="process")
        assert sorted(result) == [11, 21]

    def test_max_workers(self):
        result = parallel_map(str, [1, 2, 3, 4], mode="thread", max_workers=2)
        assert sorted(result) == ["1", "2", "3", "4"]


# ---------------------------------------------------------------------------
# parallel_map_async
# ---------------------------------------------------------------------------

class TestParallelMapAsync:
    def test_async_basic(self):
        async def double(x):
            return x * 2

        result = asyncio.run(parallel_map_async(double, [1, 2, 3]))
        assert sorted(result) == [2, 4, 6]

    def test_batch_size(self):
        async def inc(x):
            return x + 1

        result = asyncio.run(parallel_map_async(inc, list(range(20)), batch_size=5))
        assert sorted(result) == list(range(1, 21))


# ---------------------------------------------------------------------------
# parallel_map_async_safe
# ---------------------------------------------------------------------------

class TestParallelMapAsyncSafe:
    def test_all_success(self):
        async def fn(x):
            return x * 3

        results, errors = asyncio.run(parallel_map_async_safe(fn, [1, 2]))
        assert sorted(results) == [3, 6]
        assert errors == []

    def test_captures_errors(self):
        async def fn(x):
            if x == 2:
                raise ValueError("bad")
            return x

        results, errors = asyncio.run(parallel_map_async_safe(fn, [1, 2, 3]))
        assert 1 in results
        assert 3 in results
        assert len(errors) == 1
        assert "bad" in str(errors[0])


# ---------------------------------------------------------------------------
# _verify_picklable
# ---------------------------------------------------------------------------

class TestVerifyPicklable:
    def test_picklable_object(self):
        _verify_picklable(42)  # should not raise
        _verify_picklable("hello")
        _verify_picklable([1, 2, 3])

    def test_unpicklable_raises(self):
        import threading
        lock = threading.Lock()
        with pytest.raises(TypeError):
            _verify_picklable(lock)


# ---------------------------------------------------------------------------
# DownloadCache
# ---------------------------------------------------------------------------

class TestDownloadCache:
    def test_cache_hit(self):
        cache = DownloadCache()
        cache.put("http://example.com/a.mp4", "/tmp/a.mp4")
        assert cache.get("http://example.com/a.mp4") == "/tmp/a.mp4"

    def test_cache_miss(self):
        cache = DownloadCache()
        assert cache.get("http://example.com/missing") is None

    def test_dedup(self):
        cache = DownloadCache()
        assert cache.seen("http://x.com/1") is False
        cache.put("http://x.com/1", "/tmp/1")
        assert cache.seen("http://x.com/1") is True
        # Second put should be a no-op (already exists)
        cache.put("http://x.com/1", "/tmp/1_dup")
        assert cache.get("http://x.com/1") == "/tmp/1"
