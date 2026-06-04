"""Tests for builderpulse.batch.disk_guard — DiskGuard."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from builderpulse.batch.disk_guard import DiskFullError, DiskGuard


class TestDiskGuardCheck:
    """check() behavior."""

    def test_check_passes_when_space_available(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1)  # 1 byte minimum
        # Should not raise
        guard.check(tmp_path)

    def test_check_raises_disk_full(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=2**63)  # unreasonably large
        with pytest.raises(DiskFullError):
            guard.check(tmp_path)

    def test_check_normalizes_path(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1)
        # Use a string path — should be resolved internally
        guard.check(str(tmp_path))

    def test_check_caches_result(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1, check_interval=60)
        guard.check(tmp_path)
        # Second call should use cache (no exception)
        guard.check(tmp_path)
        # Verify cache is populated
        assert guard._cached_result is True

    def test_check_cache_expires(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1, check_interval=0)
        guard.check(tmp_path)
        # With 0 interval, cache should expire immediately
        import time
        time.sleep(0.01)
        guard.check(tmp_path)  # should re-check, still pass


class TestDiskGuardWaitForSpace:
    """wait_for_space (sync)."""

    def test_wait_for_space_immediate(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1, check_interval=0)
        # Should return immediately since space is available
        guard.wait_for_space(str(tmp_path), poll=0.01)


class TestDiskGuardWaitForSpaceAsync:
    """wait_for_space_async."""

    @pytest.mark.asyncio
    async def test_wait_for_space_async_immediate(self, tmp_path: Path) -> None:
        guard = DiskGuard(min_bytes=1, check_interval=0)
        await guard.wait_for_space_async(str(tmp_path), poll=0.01)
