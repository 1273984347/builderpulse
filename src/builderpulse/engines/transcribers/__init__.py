"""Transcriber auto-detection."""

from __future__ import annotations

import importlib
import logging

from .base import Transcriber

__all__ = [
    "Transcriber",
    "get_transcriber",
]

logger = logging.getLogger("builderpulse.transcribers")


# Map engine name → top-level PyPI package name that backs it. Probing
# this lets us distinguish "engine not installed" (ImportError, caught by
# the auto loop) from "ffmpeg missing" (RuntimeError, surfaces explicitly).
_ENGINE_PYPI_PACKAGES = {
    "whisper": "whisper",
    "whisperx": "whisperx",
    "faster_whisper": "faster_whisper",
}


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
    if name not in _ENGINE_PYPI_PACKAGES:
        raise ValueError(
            f"Unknown engine: {name}. Valid: {', '.join(_ENGINE_PYPI_PACKAGES)}"
        )

    # 2. Probe whether the engine's PyPI package is installed. If not,
    #    raise ImportError so the auto loop's `except ImportError` can try
    #    the next engine. This must happen BEFORE the ffmpeg check — the
    #    `from .X import X` lines below succeed regardless of whether the
    #    PyPI package is installed (because the wrapper source module is
    #    part of this project), so they cannot be used to detect
    #    "engine not available".
    pypi_pkg = _ENGINE_PYPI_PACKAGES[name]
    try:
        importlib.import_module(pypi_pkg)
    except ImportError as e:
        raise ImportError(
            f"{pypi_pkg} not installed. "
            f"Run: pip install builderpulse[{name.replace('_', '-')}]"
        ) from e

    # 3. Verify ffmpeg is available before instantiating the engine.
    #    (P1 fix: fail fast rather than crashing later in the transcribe
    #    call with a confusing subprocess error.)
    from builderpulse.infra.platform_compat import find_ffmpeg

    if not find_ffmpeg():
        raise RuntimeError(
            "FFmpeg not found. Install it: https://ffmpeg.org/download.html"
        )

    # 4. Instantiate the engine class.
    if name == "whisper":
        from .whisper import WhisperTranscriber

        return WhisperTranscriber(model=model, device=device)
    elif name == "whisperx":
        from .whisperx import WhisperXTranscriber

        return WhisperXTranscriber(model=model, device=device)
    else:  # faster_whisper
        from .faster_whisper import FasterWhisperTranscriber

        return FasterWhisperTranscriber(model=model, device=device)
