"""Transcriber auto-detection."""

from __future__ import annotations

import logging

from .base import Transcriber

__all__ = [
    "Transcriber",
    "get_transcriber",
]

logger = logging.getLogger("builderpulse.transcribers")


def get_transcriber(
    engine: str = "auto",
    model: str = "base",
    device: str = "cpu",
) -> Transcriber:
    """Get a transcriber instance. Auto-detects available engine if engine="auto"."""
    if engine == "auto":
        for name in ["faster_whisper", "whisperx", "whisper"]:
            try:
                return _load_engine(name, model=model, device=device)
            except ImportError as e:
                logger.debug(f"Engine {name} unavailable: {e}")
                continue
        raise ImportError(
            "No transcription engine installed. "
            "Install one of: pip install builderpulse[faster-whisper] | [whisper] | [whisperx]"
        )
    return _load_engine(engine, model=model, device=device)


def _load_engine(name: str, model: str = "base", device: str = "cpu") -> Transcriber:
    # Validate name first (cheap check) so callers get a clear ValueError on typos
    # before we touch the filesystem / ffmpeg.
    if name not in ("whisper", "whisperx", "faster_whisper"):
        raise ValueError(
            f"Unknown engine: {name}. Valid: whisper, whisperx, faster_whisper"
        )

    # P1 fix: verify ffmpeg is available before instantiating the engine.
    # Done after name validation so that unknown-engine errors surface first
    # regardless of platform tooling, and so the auto-detection loop can
    # distinguish "no engine installed" (ImportError) from "ffmpeg missing"
    # (RuntimeError).
    from builderpulse.infra.platform_compat import find_ffmpeg

    if not find_ffmpeg():
        raise RuntimeError(
            "FFmpeg not found. Install it: https://ffmpeg.org/download.html"
        )

    if name == "whisper":
        from .whisper import WhisperTranscriber

        return WhisperTranscriber(model=model, device=device)
    elif name == "whisperx":
        from .whisperx import WhisperXTranscriber

        return WhisperXTranscriber(model=model, device=device)
    else:  # faster_whisper
        from .faster_whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber(model=model, device=device)
