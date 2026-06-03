"""Tests for transcriber auto-detection and real transcription."""
from pathlib import Path

import pytest

from builderpulse.engines.transcribers import get_transcriber
from builderpulse.core.models import TranscriptResult


def test_get_transcriber_unknown_engine():
    with pytest.raises(ValueError, match="Unknown engine"):
        get_transcriber("nonexistent")


def test_get_transcriber_auto_no_engines(monkeypatch):
    """When no engines are installed, auto should raise ImportError."""
    try:
        import whisper  # noqa: F401
        pytest.skip("whisper is installed, cannot test auto-detect failure")
    except ImportError:
        try:
            import faster_whisper  # noqa: F401
            pytest.skip("faster-whisper is installed, cannot test auto-detect failure")
        except ImportError:
            with pytest.raises(ImportError, match="No transcription engine"):
                get_transcriber("auto")


@pytest.fixture
def silence_wav(tmp_path):
    """Create a 3-second silence WAV file for testing."""
    import wave
    import struct

    path = tmp_path / "silence.wav"
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 48000, *([0] * 48000)))
    return path


def test_faster_whisper_real_transcribe(silence_wav):
    """Real transcription test with faster-whisper (silence input)."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        pytest.skip("faster-whisper not installed")

    transcriber = get_transcriber("faster-whisper")
    assert transcriber.name == "faster-whisper"

    result = transcriber.transcribe(silence_wav, language="en")

    assert isinstance(result, TranscriptResult)
    assert result.engine == "faster-whisper"
    assert result.language == "en"
    # Silence should produce empty or very short text
    assert isinstance(result.text, str)
    assert isinstance(result.segments, list)
    print(f"Transcribed silence: '{result.text}' ({len(result.segments)} segments)")


def test_faster_whisper_auto_detect(silence_wav):
    """Auto-detect should find faster-whisper when installed."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        pytest.skip("faster-whisper not installed")

    transcriber = get_transcriber("auto")
    assert transcriber.name == "faster-whisper"

    result = transcriber.transcribe(silence_wav)
    assert isinstance(result, TranscriptResult)
    print(f"Auto-detect engine: {result.engine}")
