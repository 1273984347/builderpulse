"""OpenAI Whisper transcriber."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from builderpulse.core.models import TranscriptResult
from .base import Transcriber


class WhisperTranscriber(Transcriber):
    def __init__(self, model: str = "base", device: str = "cpu"):
        self._model_name = model
        self._device = device
        try:
            import whisper  # noqa: F401
            self._model = None  # lazy load
        except ImportError:
            raise ImportError(
                "openai-whisper not installed. Run: pip install builderpulse[whisper]"
            )

    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> TranscriptResult:
        import whisper

        if self._model is None:
            self._model = whisper.load_model(self._model_name, device=self._device)
        result = self._model.transcribe(str(audio_path), language=language)
        return TranscriptResult(
            text=result["text"],
            language=result.get("language", "unknown"),
            engine="whisper",
            segments=result.get("segments", []),
        )

    @property
    def name(self) -> str:
        return "whisper"
