"""Faster Whisper transcriber."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from builderpulse.core.models import TranscriptResult
from .base import Transcriber


class FasterWhisperTranscriber(Transcriber):
    def __init__(self, model: str = "base", device: str = "cpu"):
        self._model_name = model
        self._device = device
        try:
            from faster_whisper import WhisperModel  # noqa: F401

            self._model = None  # lazy load
        except ImportError:
            raise ImportError(
                "faster-whisper not installed. Run: pip install builderpulse[faster-whisper]"
            )

    def transcribe(
        self, audio_path: Path, language: Optional[str] = None
    ) -> TranscriptResult:
        from faster_whisper import WhisperModel

        if self._model is None:
            self._model = WhisperModel(self._model_name, device=self._device)
        segments_raw, info = self._model.transcribe(str(audio_path), language=language)
        segments = [
            {"start": s.start, "end": s.end, "text": s.text} for s in segments_raw
        ]
        text = " ".join(s["text"] for s in segments)
        return TranscriptResult(
            text=text,
            language=info.language if language is None else language,
            engine="faster_whisper",
            segments=segments,
        )

    @property
    def name(self) -> str:
        return "faster_whisper"
