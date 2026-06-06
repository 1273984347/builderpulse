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
    # 1. Validate name (cheap, no side effects) so unknown-engine errors
    #    surface immediately, independent of platform tooling.
    if name not in ("whisper", "whisperx", "faster_whisper"):
        raise ValueError(
            f"Unknown engine: {name}. Valid: whisper, whisperx, faster_whisper"
        )

    # 2. Import the engine module BEFORE checking ffmpeg. If the engine
    #    isn't installed, the ImportError will propagate to the auto loop's
    #    `except ImportError`, letting it try the next engine. If we
    #    checked ffmpeg first, a missing ffmpeg would raise RuntimeError
    #    that the auto loop does not catch — making it impossible to
    #    distinguish "no engine" from "ffmpeg missing" in `auto` mode.
    if name == "whisper":
        from .whisper import WhisperTranscriber

        cls = WhisperTranscriber
    elif name == "whisperx":
        from .whisperx import WhisperXTranscriber

        cls = WhisperXTranscriber
    else:  # faster_whisper
        from .faster_whisper import FasterWhisperTranscriber

        cls = FasterWhisperTranscriber

    # 3. Verify ffmpeg is available before instantiating the engine.
    #    (P1 fix: fail fast rather than crashing later in the transcribe
    #    call with a confusing subprocess error.)
    from builderpulse.infra.platform_compat import find_ffmpeg

    if not find_ffmpeg():
        raise RuntimeError(
            "FFmpeg not found. Install it: https://ffmpeg.org/download.html"
        )

    return cls(model=model, device=device)
