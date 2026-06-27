"""
Tests for UniversalAdapterProvider in remix/summarizer.py.

Verifies:
1. Class imports correctly
2. get_provider("u:...") routes to UniversalAdapterProvider
3. get_provider("auto") prefers UniversalAdapterProvider when available
4. Backward compat: existing claude/gpt/ollama routing unchanged
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from either C:/tmp (standalone) or builderpulse/tests/ (installed)
_THIS_DIR = Path(__file__).parent.resolve()
if str(_THIS_DIR.parent / "src") not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent / "src"))


def test_universal_adapter_provider_class_exists():
    """UniversalAdapterProvider should be importable from summarizer module."""
    from builderpulse.remix.summarizer import UniversalAdapterProvider
    assert UniversalAdapterProvider is not None


def test_get_provider_u_prefix_routes_to_universal():
    """get_provider('u:gpt-4o-mini') should return UniversalAdapterProvider."""
    from builderpulse.remix.summarizer import get_provider, UniversalAdapterProvider
    provider = get_provider("u:gpt-4o-mini")
    assert isinstance(provider, UniversalAdapterProvider), (
        f"u: prefix should route to UniversalAdapterProvider, got {type(provider).__name__}"
    )
    assert provider.model == "gpt-4o-mini"


def test_get_provider_u_prefix_strips_correctly():
    """get_provider('u:claude-sonnet-4-5') should keep 'claude-sonnet-4-5' as model."""
    from builderpulse.remix.summarizer import get_provider, UniversalAdapterProvider
    provider = get_provider("u:claude-sonnet-4-5")
    assert isinstance(provider, UniversalAdapterProvider)
    assert provider.model == "claude-sonnet-4-5"


def test_get_provider_auto_prefers_universal():
    """get_provider('auto') with universal_adapter installed should prefer UniversalAdapterProvider."""
    from builderpulse.remix.summarizer import get_provider, UniversalAdapterProvider
    provider = get_provider("auto")
    assert isinstance(provider, UniversalAdapterProvider), (
        f"'auto' should prefer UniversalAdapterProvider when installed, got {type(provider).__name__}"
    )


def test_backward_compat_claude_still_routes_to_anthropic():
    """get_provider('claude-*') should still return AnthropicProvider (not UniversalAdapter)."""
    from builderpulse.remix.summarizer import get_provider, AnthropicProvider
    provider = get_provider("claude-sonnet-4-5")
    assert isinstance(provider, AnthropicProvider), (
        f"'claude-*' should still route to AnthropicProvider for backward compat, "
        f"got {type(provider).__name__}"
    )


def test_backward_compat_gpt_still_routes_to_openai():
    """get_provider('gpt-*') should still return OpenAIProvider."""
    from builderpulse.remix.summarizer import get_provider, OpenAIProvider
    provider = get_provider("gpt-4o")
    assert isinstance(provider, OpenAIProvider), (
        f"'gpt-*' should still route to OpenAIProvider for backward compat, "
        f"got {type(provider).__name__}"
    )


def test_backward_compat_ollama_still_routes_to_ollama():
    """get_provider('ollama/*') should still return OllamaProvider."""
    from builderpulse.remix.summarizer import get_provider, OllamaProvider
    provider = get_provider("ollama/llama3")
    assert isinstance(provider, OllamaProvider)


def test_unknown_model_raises():
    """Unknown model prefix should raise ValueError."""
    from builderpulse.remix.summarizer import get_provider
    import pytest
    with pytest.raises(ValueError, match="Unknown model"):
        get_provider("random-unknown-model")


def test_universal_provider_complete_returns_string():
    """UniversalAdapterProvider.complete() should return str (sync wrapper contract).

    This test uses OpenAI-compatible endpoint or stubs. With no API key,
    it will raise — that's expected. We just check the interface contract.
    """
    from builderpulse.remix.summarizer import UniversalAdapterProvider
    provider = UniversalAdapterProvider(model="gpt-4o-mini", api_key="")
    # complete() is synchronous — must return str (not await)
    # Without API key, will raise on actual call; just verify callable
    assert callable(provider.complete)
    # Type hint contract check
    import inspect
    sig = inspect.signature(provider.complete)
    assert "prompt" in sig.parameters
    assert "system" in sig.parameters
    assert "temperature" in sig.parameters


def test_summarizer_uses_universal_provider_via_get_provider():
    """Summarizer should work with UniversalAdapterProvider via get_provider('auto')."""
    from builderpulse.remix.summarizer import get_provider, Summarizer, UniversalAdapterProvider
    provider = get_provider("auto")
    summarizer = Summarizer(provider=provider, chunk_size=100)
    assert isinstance(summarizer.provider, UniversalAdapterProvider)
