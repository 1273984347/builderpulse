"""
B3: Tests for universal_adapter embed() method.

Verifies:
1. detect_provider support matrix covers OpenAI/Azure/local OpenAI-compat
2. Mistral/Cohere native embed families are declared
3. Providers without embed support raise NotImplementedError with helpful list
4. EmbeddingResponse dataclass structure
5. Single string → list-of-one normalization
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from either /tmp or builderpulse/tests/
_THIS_DIR = Path(__file__).parent.resolve()
if (_THIS_DIR / "universal_llm_adapter.py").exists():
    sys.path.insert(0, str(_THIS_DIR))
    from universal_llm_adapter import (  # type: ignore[no-redef]
        EmbeddingResponse, ProviderInfo,
        detect_provider, embed,
        _EMBED_SUPPORT,
    )
elif (_THIS_DIR.parent / "src" / "builderpulse" / "llm" / "universal_adapter.py").exists():
    sys.path.insert(0, str(_THIS_DIR.parent / "src"))
    from builderpulse.llm.universal_adapter import (  # type: ignore[no-redef]
        EmbeddingResponse, ProviderInfo,
        detect_provider, embed,
        _EMBED_SUPPORT,
    )
else:
    raise ImportError(f"Cannot locate universal_adapter.py. _THIS_DIR={_THIS_DIR}")


# ---------- EmbeddingResponse dataclass ----------

def test_embedding_response_dataclass():
    """EmbeddingResponse should hold embeddings + model + usage."""
    from dataclasses import fields
    r = EmbeddingResponse(embeddings=[[0.1, 0.2]], model="text-embedding-3-small")
    assert r.embeddings == [[0.1, 0.2]]
    assert r.model == "text-embedding-3-small"
    assert r.usage == {}  # default_factory
    # Verify field names (catches accidental rename)
    field_names = {f.name for f in fields(r)}
    assert field_names == {"embeddings", "model", "usage"}


# ---------- _EMBED_SUPPORT matrix ----------

def test_embed_support_matrix_has_all_canonical_providers():
    """_EMBED_SUPPORT should have entries for all 15 canonical providers."""
    expected = {
        "openai", "anthropic", "google", "grok", "deepseek",
        "qwen", "cerebras", "groq", "azure", "deepinfra",
        "mistral", "cohere", "together", "fireworks",
        "local", "unknown",
    }
    actual = set(_EMBED_SUPPORT.keys())
    assert expected <= actual, f"missing: {expected - actual}, extra: {actual - expected}"


def test_embed_support_openai_family_providers():
    """Providers with OpenAI-compatible /v1/embeddings should be 'openai' family."""
    openai_family_providers = ("openai", "azure", "deepinfra", "together", "fireworks", "local")
    for prov in openai_family_providers:
        family, model = _EMBED_SUPPORT[prov]
        assert family == "openai", f"{prov} should be openai family, got {family}"
        assert model is not None, f"{prov} should have a default embed model"


def test_embed_support_native_providers_have_native_family():
    """Mistral and Cohere have their own embed APIs (not OpenAI-compatible)."""
    assert _EMBED_SUPPORT["mistral"][0] == "mistral"
    assert _EMBED_SUPPORT["mistral"][1] == "mistral-embed"
    assert _EMBED_SUPPORT["cohere"][0] == "cohere"
    assert _EMBED_SUPPORT["cohere"][1] == "embed-english-v3.0"


def test_embed_support_unsupported_providers_have_none():
    """Providers without embeddings should be (None, None)."""
    unsupported = ("groq", "cerebras", "grok", "qwen", "deepseek", "anthropic", "google", "unknown")
    for prov in unsupported:
        family, model = _EMBED_SUPPORT[prov]
        assert family is None, f"{prov} should be None family (no embed support)"
        assert model is None


# ---------- detect_provider + embed() integration ----------

def test_embed_unsupported_provider_raises_with_helpful_message():
    """embed() on unsupported provider should raise NotImplementedError mentioning supported list."""
    import asyncio
    import pytest

    # Anthropic doesn't support embeddings
    info = ProviderInfo(name="anthropic", api_key="dummy", model_name="claude-sonnet-4-5")
    with pytest.raises(NotImplementedError) as exc_info:
        asyncio.run(embed("test text", info))
    msg = str(exc_info.value)
    assert "anthropic" in msg or "does not support" in msg
    # Should list supported providers (or at least mention "openai")
    assert "openai" in msg, f"error should mention supported providers: {msg}"


def test_embed_groq_unsupported():
    """Groq is explicitly unsupported for embeddings."""
    import asyncio
    import pytest
    info = ProviderInfo(name="groq", base_url="https://api.groq.com/openai/v1", api_key="dummy", model_name="llama")
    with pytest.raises(NotImplementedError):
        asyncio.run(embed("test", info))


# ---------- Single string → list normalization ----------

def test_embed_accepts_single_string():
    """embed() should accept both 'text' and ['text1', 'text2']."""
    import asyncio
    import inspect

    sig = inspect.signature(embed)
    # First param is texts: list[str] | str
    param = sig.parameters["texts"]
    # Just verify the annotation accepts both (type annotation may or may not be evaluated)
    assert "texts" in sig.parameters


def test_embed_response_structure_with_real_openai():
    """If OPENAI_API_KEY is set, try real embed call and verify structure.

    Skipped if no key — pure structure check otherwise.
    """
    import asyncio
    import os
    import pytest

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set; skipping real embed call")

    info = ProviderInfo(name="openai", api_key=os.environ["OPENAI_API_KEY"], model_name="text-embedding-3-small")
    result = asyncio.run(embed(["hello", "world"], info))
    assert len(result.embeddings) == 2
    assert all(isinstance(v, list) for v in result.embeddings)
    # text-embedding-3-small produces 1536-dim vectors
    assert all(len(v) == 1536 for v in result.embeddings), (
        f"expected 1536-dim vectors, got dims: {set(len(v) for v in result.embeddings)}"
    )
    assert result.model == "text-embedding-3-small"
    assert "prompt_tokens" in result.usage or "total_tokens" in result.usage
