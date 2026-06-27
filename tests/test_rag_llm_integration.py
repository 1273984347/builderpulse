"""
Tests for RAGChannel LLM integration (llm_summarize + llm_rerank).

Verifies:
1. llm_summarize / llm_rerank fall back to non-LLM versions when no provider set
2. llm_provider parameter is stored correctly
3. Method signatures accept expected arguments
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from builderpulse/tests/ (installed mode)
_THIS_DIR = Path(__file__).parent.resolve()
if str(_THIS_DIR.parent / "src") not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent / "src"))


def test_rag_channel_accepts_llm_provider():
    """RAGChannel.__init__ should accept llm_provider parameter (default None)."""
    from builderpulse.rag.channel import RAGChannel
    # We can't easily instantiate without qdrant running; check signature only
    import inspect
    sig = inspect.signature(RAGChannel.__init__)
    assert "llm_provider" in sig.parameters, (
        "RAGChannel should accept llm_provider parameter"
    )
    # Default should be None (backward compat)
    assert sig.parameters["llm_provider"].default is None


def test_llm_summarize_fallback_when_no_provider():
    """llm_summarize should fall back to summarize() when llm_provider is None.

    Uses unittest.mock to bypass qdrant requirement — we mock RAGChannel
    with no real qdrant connection, then test the method logic.
    """
    from unittest.mock import MagicMock, patch
    from builderpulse.rag.channel import RAGChannel

    # Create RAGChannel-like object without triggering qdrant connection
    channel = MagicMock(spec=RAGChannel)
    channel.llm_provider = None  # explicitly None
    # Pre-populate method by binding
    channel.summarize = RAGChannel.summarize.__get__(channel)
    channel.llm_summarize = RAGChannel.llm_summarize.__get__(channel)

    sample_results = [
        {"id": "1", "score": 0.95, "text": "Khoj is an AI second brain.", "metadata": {}},
        {"id": "2", "score": 0.80, "text": "Universal LLM adapter supports 15 providers.", "metadata": {}},
    ]
    out = channel.llm_summarize("What is Khoj?", sample_results, max_items=2)
    # Fallback path: same output as summarize()
    assert "Khoj" in out
    assert "Top" in out
    # LLM-specific phrase should NOT be present (fallback mode)
    assert "Based on the context" not in out


def test_llm_summarize_uses_provider_when_set():
    """llm_summarize should call llm_provider.complete() when provider is set."""
    from unittest.mock import MagicMock
    from builderpulse.rag.channel import RAGChannel

    # Mock provider that returns a deterministic answer
    mock_provider = MagicMock()
    mock_provider.complete.return_value = "Based on context, Khoj is an AI second brain. [1]"

    channel = MagicMock(spec=RAGChannel)
    channel.llm_provider = mock_provider
    channel.llm_summarize = RAGChannel.llm_summarize.__get__(channel)

    sample_results = [
        {"id": "1", "score": 0.95, "text": "Khoj is an AI second brain.", "metadata": {}},
    ]
    out = channel.llm_summarize("What is Khoj?", sample_results, max_items=2)

    # Provider called exactly once with correct args
    mock_provider.complete.assert_called_once()
    call_args = mock_provider.complete.call_args
    prompt_arg = call_args[0][0]  # first positional arg
    assert "Question: What is Khoj?" in prompt_arg
    assert "based ONLY on the context" in prompt_arg  # actual prompt uses lowercase 'b'
    assert "Khoj is an AI second brain." in prompt_arg

    # Output is provider's response
    assert out == "Based on context, Khoj is an AI second brain. [1]"


def test_llm_rerank_fallback_when_no_provider():
    """llm_rerank should fall back to rerank_by_keywords() when provider is None."""
    from unittest.mock import MagicMock
    from builderpulse.rag.channel import RAGChannel

    channel = MagicMock(spec=RAGChannel)
    channel.llm_provider = None
    channel.rerank_by_keywords = RAGChannel.rerank_by_keywords.__get__(channel)
    channel.llm_rerank = RAGChannel.llm_rerank.__get__(channel)

    sample_results = [
        {"id": "1", "score": 0.5, "text": "Khoj supports universal adapter", "metadata": {}},
        {"id": "2", "score": 0.5, "text": "Other irrelevant text", "metadata": {}},
    ]
    out = channel.llm_rerank("universal adapter", sample_results, top_k=2)

    # Fallback path uses keyword overlap scoring
    assert len(out) == 2
    assert "rerank_score" in out[0]
    # First result should have higher score (more keyword overlap)
    assert out[0]["rerank_score"] >= out[1]["rerank_score"]


def test_llm_rerank_uses_provider_when_set():
    """llm_rerank should call provider.complete() for each result."""
    from unittest.mock import MagicMock
    from builderpulse.rag.channel import RAGChannel

    # Mock provider returns "8" for first, "3" for second
    mock_provider = MagicMock()
    mock_provider.complete.side_effect = ["8", "3"]

    channel = MagicMock(spec=RAGChannel)
    channel.llm_provider = mock_provider
    channel.llm_rerank = RAGChannel.llm_rerank.__get__(channel)

    sample_results = [
        {"id": "1", "score": 0.5, "text": "Khoj supports universal adapter", "metadata": {}},
        {"id": "2", "score": 0.5, "text": "Other irrelevant text", "metadata": {}},
    ]
    out = channel.llm_rerank("universal adapter", sample_results, top_k=2)

    # Provider called once per result
    assert mock_provider.complete.call_count == 2
    # Both results have llm_relevance_score
    assert "llm_relevance_score" in out[0]
    assert "llm_relevance_score" in out[1]
    # Sorted by score desc: 8 > 3
    assert out[0]["llm_relevance_score"] == 8.0
    assert out[1]["llm_relevance_score"] == 3.0
    assert out[0]["id"] == "1"


def test_llm_rerank_handles_malformed_provider_response():
    """llm_rerank should default to 0 on parse failure (graceful degradation)."""
    from unittest.mock import MagicMock
    from builderpulse.rag.channel import RAGChannel

    # Provider returns unparseable response
    mock_provider = MagicMock()
    mock_provider.complete.return_value = "not a number at all"

    channel = MagicMock(spec=RAGChannel)
    channel.llm_provider = mock_provider
    channel.llm_rerank = RAGChannel.llm_rerank.__get__(channel)

    sample_results = [{"id": "1", "score": 0.5, "text": "test", "metadata": {}}]
    out = channel.llm_rerank("query", sample_results, top_k=1)

    # Graceful degradation: score = 0, no crash
    assert out[0]["llm_relevance_score"] == 0.0


def test_universal_adapter_integration_smoke():
    """End-to-end: instantiate UniversalAdapterProvider + RAGChannel (no qdrant).

    Skips actual LLM call (uses stub provider) but verifies wiring works.
    """
    from unittest.mock import MagicMock
    from builderpulse.rag.channel import RAGChannel
    from builderpulse.remix.summarizer import get_provider, UniversalAdapterProvider

    # Verify UniversalAdapterProvider class is importable from remix (B session deliverable)
    assert UniversalAdapterProvider is not None

    # Verify 'u:' prefix routes correctly (already tested in test_universal_provider.py,
    # but verify here for cross-module integration)
    provider = get_provider("u:groq/llama-3.1-70b")
    assert isinstance(provider, UniversalAdapterProvider)
    assert provider.model == "groq/llama-3.1-70b"

    # RAGChannel accepts this provider via __init__ (signature check)
    import inspect
    sig = inspect.signature(RAGChannel.__init__)
    assert "llm_provider" in sig.parameters
