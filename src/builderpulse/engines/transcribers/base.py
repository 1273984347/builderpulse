"""Abstract base class for transcribers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from builderpulse.core.models import TranscriptResult


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> TranscriptResult:
        """Transcribe audio file to text."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name."""
        ...
