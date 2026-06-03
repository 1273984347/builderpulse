"""Abstract base class for video/audio downloaders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from builderpulse.core.models import SourceRef, DownloadResult


class Downloader(ABC):
    """Base class for all downloaders."""

    @abstractmethod
    def download(self, source: SourceRef, output_dir: Path) -> DownloadResult:
        """Download content from source. Returns DownloadResult."""
        ...

    @abstractmethod
    def can_handle(self, source: SourceRef) -> bool:
        """Check if this downloader can handle the given source."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Downloader name for logging."""
        ...
