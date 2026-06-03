"""Tests for transcriber auto-detection."""
import pytest

from builderpulse.engines.transcribers import get_transcriber


def test_get_transcriber_unknown_engine():
    with pytest.raises(ValueError, match="Unknown engine"):
        get_transcriber("nonexistent")


def test_get_transcriber_auto_no_engines(monkeypatch):
    """When no engines are installed, auto should raise ImportError."""
    try:
        import whisper  # noqa: F401
        pytest.skip("whisper is installed, cannot test auto-detect failure")
    except ImportError:
        with pytest.raises(ImportError, match="No transcription engine"):
            get_transcriber("auto")
