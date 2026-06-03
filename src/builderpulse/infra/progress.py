"""Progress reporting for CLI and MCP."""
from __future__ import annotations
import sys
from typing import Optional

class ProgressReporter:
    """Simple progress reporter."""

    def __init__(self, total: int, desc: str = ""):
        self.total = total
        self.current = 0
        self.desc = desc

    def update(self, n: int = 1, desc: str | None = None):
        self.current += n
        if desc:
            self.desc = desc

    @property
    def percent(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass
