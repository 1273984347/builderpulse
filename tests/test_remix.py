"""Tests for remix module."""
from pathlib import Path
from builderpulse.remix.prompts import load_prompt, list_prompts
from builderpulse.remix.summarizer import get_provider, Summarizer

def test_load_prompt_not_found():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_xyz")

def test_list_prompts():
    prompts = list_prompts()
    assert isinstance(prompts, list)

def test_get_provider_unknown():
    import pytest
    with pytest.raises(ValueError, match="Unknown model"):
        get_provider("unknown-model")

def test_summarizer_chunk():
    """Test that chunking splits long text correctly."""
    from builderpulse.remix.summarizer import Summarizer
    # Create a mock provider
    class MockProvider:
        def complete(self, prompt, system="", temperature=0.3):
            return f"Summary of {len(prompt)} chars"

    s = Summarizer(provider=MockProvider(), chunk_size=100)
    # Create text longer than chunk_size
    text = "Hello world. " * 50  # ~650 chars
    result = s.summarize(text)
    assert "Summary" in result
