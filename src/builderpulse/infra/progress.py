"""Progress reporting for CLI and MCP.

Provides two implementations:
- ``RichProgress`` — uses ``rich.progress.Progress`` when stdout is a TTY.
- ``TextProgress`` — simple "42% (3/10) ETA 2m" fallback for non-TTY / MCP.

``create_progress(**kwargs)`` is the recommended factory.
"""
from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from typing import Optional


class ProgressBase(ABC):
    """Common interface for progress reporters."""

    def __init__(self, total: int, desc: str = "") -> None:
        self.total = total
        self.current = 0
        self.desc = desc
        self._start_time = time.monotonic()

    def update(self, n: int = 1, desc: str | None = None) -> None:
        self.current += n
        if desc:
            self.desc = desc
        self._on_update()

    @property
    def percent(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimated seconds remaining, or ``None`` if not enough data."""
        if self.current <= 0 or self.total <= 0:
            return None
        rate = self.elapsed / self.current
        remaining = self.total - self.current
        return rate * remaining

    def __enter__(self) -> ProgressBase:
        self._start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._finish()

    @abstractmethod
    def _start(self) -> None: ...

    @abstractmethod
    def _on_update(self) -> None: ...

    @abstractmethod
    def _finish(self) -> None: ...


# ---------------------------------------------------------------------------
# Rich progress  (TTY mode)
# ---------------------------------------------------------------------------

class RichProgress(ProgressBase):
    """Progress bar powered by ``rich.progress.Progress``."""

    def __init__(self, total: int, desc: str = "") -> None:
        super().__init__(total, desc)
        self._progress = None
        self._task_id = None

    def _start(self) -> None:
        try:
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )
            self._progress = Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
            self._progress.start()
            self._task_id = self._progress.add_task(self.desc, total=self.total)
        except ImportError:
            # rich not available — fall back to text mode
            self._progress = None

    def _on_update(self) -> None:
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=self.current, description=self.desc)

    def _finish(self) -> None:
        if self._progress is not None:
            self._progress.stop()


# ---------------------------------------------------------------------------
# Text progress  (non-TTY / MCP mode)
# ---------------------------------------------------------------------------

class TextProgress(ProgressBase):
    """Simple ``"42% (3/10) ETA 2m"`` output to stderr."""

    def _start(self) -> None:
        self._print_line()

    def _on_update(self) -> None:
        self._print_line()

    def _finish(self) -> None:
        self._print_line()
        sys.stderr.write("\n")

    def _print_line(self) -> None:
        eta = self.eta_seconds
        if eta is not None:
            eta_str = _format_duration(eta)
        else:
            eta_str = "?"
        line = f"\r{self.percent:.0f}% ({self.current}/{self.total}) ETA {eta_str}"
        sys.stderr.write(line)
        sys.stderr.flush()


def _format_duration(seconds: float) -> str:
    """Format *seconds* as a human-readable string like ``2m 15s``."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_progress(
    total: int,
    desc: str = "",
    *,
    force_text: bool = False,
) -> ProgressBase:
    """Return a ``RichProgress`` (TTY) or ``TextProgress`` (non-TTY).

    Pass ``force_text=True`` to always use the text fallback.
    """
    if force_text:
        return TextProgress(total, desc)

    if sys.stdout.isatty():
        return RichProgress(total, desc)

    return TextProgress(total, desc)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

ProgressReporter = TextProgress  # alias for legacy callers
