"""Transcriber auto-detection."""
from __future__ import annotations

import logging
from typing import Optional

from .base import Transcriber
from .whisper import WhisperTranscriber
from .whisperx import WhisperXTranscriber
from .faster_whisper import FasterWhisperTranscriber

__all__ = [
    "Transcriber",
    "get_transcriber",
    "WhisperTranscriber",
    "WhisperXTranscriber",
    "FasterWhisperTranscriber",
]

logger = logging.getLogger("builderpulse.transcribers")


def get_transcriber(engine: str = "auto") -> Transcriber:
    """Get a transcriber instance. Auto-detects available engine if engine="auto"."""
    if engine == "auto":
        for name in ["faster_whisper", "whisperx", "whisper"]:
            try:
                return _load_engine(name)
            except ImportError as e:
                logger.debug(f"Engine {name} unavailable: {e}")
                continue
        raise ImportError(
            "No transcription engine installed. "
            "Install one of: pip install builderpulse[faster-whisper] | [whisper] | [whisperx]"
        )
    return _load_engine(engine)


def _load_engine(name: str) -> Transcriber:
    if name == "whisper":
        from .whisper import WhisperTranscriber
        return WhisperTranscriber()
    elif name == "whisperx":
        from .whisperx import WhisperXTranscriber
        return WhisperXTranscriber()
    elif name == "faster_whisper":
        from .faster_whisper import FasterWhisperTranscriber
        return FasterWhisperTranscriber()
    else:
        raise ValueError(f"Unknown engine: {name}")
