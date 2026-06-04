"""Disk-space guard — prevents writes when disk is full.

Checks available space via ``shutil.disk_usage()`` and raises
:class:`DiskFullError` when free bytes fall below the configured minimum.
Results are cached for ``check_interval`` seconds to avoid hammering
the filesystem on hot paths.
"""
from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Optional


# ── Exceptions ──────────────────────────────────────────────────────────


class DiskFullError(Exception):
    """Raised when disk free space is below the configured minimum."""


# ── DiskGuard ───────────────────────────────────────────────────────────


class DiskGuard:
    """Check available disk space before writing.

    Args:
        min_bytes: Minimum free bytes required.  Default 500 MB.
        check_interval: Seconds to cache the check result.  Default 30.
    """

    def __init__(
        self,
        min_bytes: int = 500 * 1024 * 1024,
        check_interval: float = 10.0,  # P1 fix: reduced from 30s for large downloads
    ) -> None:
        self._min_bytes = min_bytes
        self._check_interval = check_interval

        # Cache state
        self._last_check: float = 0.0
        self._cached_path: Optional[str] = None
        self._cached_result: Optional[bool] = None

    def check(self, path: str | Path) -> None:
        """Raise :class:`DiskFullError` if disk is full.

        Normalizes *path* via ``Path(path).resolve()``.
        Uses cached result when ``check_interval`` has not elapsed.
        """
        resolved = str(Path(path).resolve())
        now = time.monotonic()

        # Cache hit
        if (
            self._cached_path == resolved
            and self._cached_result is not None
            and (now - self._last_check) < self._check_interval
        ):
            if not self._cached_result:
                raise DiskFullError(
                    f"Disk full: {resolved} has less than {self._min_bytes} bytes free"
                )
            return

        # Actual check
        usage = shutil.disk_usage(resolved)
        ok = usage.free >= self._min_bytes

        # Update cache
        self._last_check = now
        self._cached_path = resolved
        self._cached_result = ok

        if not ok:
            raise DiskFullError(
                f"Disk full: {resolved} has {usage.free} bytes free "
                f"(need {self._min_bytes})"
            )

    def wait_for_space(self, path: str | Path, poll: float = 30.0) -> None:
        """Block until disk has enough space.  Polls every *poll* seconds."""
        while True:
            try:
                self.check(path)
                return
            except DiskFullError:
                # Reset cache so next check re-queries
                self._cached_result = None
                time.sleep(poll)

    async def wait_for_space_async(self, path: str | Path, poll: float = 30.0) -> None:
        """Async version of :meth:`wait_for_space`."""
        while True:
            try:
                self.check(path)
                return
            except DiskFullError:
                self._cached_result = None
                await asyncio.sleep(poll)

    def force_check(self, path: str | Path) -> None:
        """Bypass cache, check disk space immediately."""
        self._last_check = 0.0
        self.check(path)
