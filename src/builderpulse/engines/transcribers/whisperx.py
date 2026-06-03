"""WhisperX transcriber."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from builderpulse.core.models import TranscriptResult
from .base import Transcriber


class WhisperXTranscriber(Transcriber):
    def __init__(self):
        try:
            import whisperx  # noqa: F401
            self._model = None  # lazy load
        except ImportError:
            raise ImportError(
                "whisperx not installed. Run: pip install builderpulse[whisperx]"
            )

    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> TranscriptResult:
        import whisperx

        if self._model is None:
            device = "cpu"
            self._model = whisperx.load_model("base", device)
        audio = whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, language=language)
        return TranscriptResult(
            text=result["text"],
            language=result.get("language", "unknown"),
            engine="whisperx",
            segments=result.get("segments", []),
        )

    @property
    def name(self) -> str:
        return "whisperx"
