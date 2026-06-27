"""
Tests for universal_llm_adapter — 14 detect_provider cases + ResponseWithThought.

Mirrors the 14 test cases verified in cycle 1 R2 review.
Will be moved to builderpulse/tests/test_llm/ once stable.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from /tmp without install
sys.path.insert(0, str(Path(__file__).parent))

from universal_llm_adapter import (  # noqa: E402
    ProviderInfo,
    ResponseWithThought,
    chat,
    detect_provider,
)


# ---------- detect_provider: 14 cases ----------

_DETECT_CASES = [
    # (label, base_url, model_name, expected_provider)
    ("cerebras-host", "https://api.cerebras.ai/v1", "llama", "cerebras"),
    ("groq-host", "https://api.groq.com/openai/v1", "llama", "groq"),
    ("grok-host", "https://api.x.ai/v1", "grok-4", "grok"),
    ("azure-subdomain", "https://my-resource.openai.azure.com/openai/deployments/gpt-4", "gpt-4", "azure"),
    ("azure-exact", "https://openai.azure.com/v1", "gpt-4", "azure"),
    ("anthropic-host", "https://api.anthropic.com/v1", "claude-sonnet-4-5", "anthropic"),
    ("google-host", "https://generativelanguage.googleapis.com/v1", "gemini-pro", "google"),
    ("anthropic-model-prefix", None, "claude-sonnet-4-5", "anthropic"),
    ("google-model-prefix", None, "gemini-2.5-flash", "google"),
    ("openai-default-no-url", None, "gpt-4o-mini", "openai"),
    ("local-host", "http://localhost:11434/v1", "llama", "local"),
    ("local-127", "http://127.0.0.1:8080/v1", "qwen", "local"),
    ("deepseek-model", None, "deepseek-reasoner", "deepseek"),
    ("qwen-host", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", "qwen"),
    ("unknown-host-and-model", "https://random.ai/v1", "unknown-model", "unknown"),
    # Cycle 6: 4 more providers
    ("mistral-host", "https://api.mistral.ai/v1", "mistral-large-latest", "mistral"),
    ("together-host", "https://api.together.xyz/v1", "meta-llama/llama-3-70b", "together"),
    ("fireworks-host", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3-70b", "fireworks"),
    ("cohere-host", "https://api.cohere.ai/v1", "command-r-plus", "cohere"),
]  # 19 cases total


def test_detect_provider_all_cases():
    """Single test that runs all 19 cases — pytest discovery will pick this up."""
    failures = []
    for label, base_url, model, expected in _DETECT_CASES:
        info = ProviderInfo(name="test", base_url=base_url, model_name=model)
        actual = detect_provider(info)
        if actual != expected:
            failures.append(f"  [{label}] expected={expected}, got={actual} (url={base_url}, model={model})")
    assert not failures, "detect_provider mismatches:\n" + "\n".join(failures)


# ---------- ResponseWithThought ----------

def test_response_with_thought_defaults():
    chunk = ResponseWithThought()
    assert chunk.text == ""
    assert chunk.thought == ""
    assert chunk.raw_content is None
    assert chunk.usage == {}
    assert isinstance(chunk.usage, dict)  # field(default_factory=dict) gives fresh dict


def test_response_with_thought_constructed():
    chunk = ResponseWithThought(text="hello", thought="thinking", usage={"tokens": 42})
    assert chunk.text == "hello"
    assert chunk.thought == "thinking"
    assert chunk.usage == {"tokens": 42}


def test_response_with_thought_independent_usage_dicts():
    """Regression: each instance must have its own usage dict, not share mutable default."""
    a = ResponseWithThought()
    b = ResponseWithThought()
    a.usage["x"] = 1
    assert "x" not in b.usage, "Mutable default leaked between instances"


# ---------- Priority ordering ----------

def test_host_takes_precedence_over_model():
    """If both hostname AND model name match different providers, hostname wins.
    Khoj pattern: detect by API base URL first, model name as fallback."""
    # api.x.ai hostname says grok; "claude-" model says anthropic → grok wins
    info = ProviderInfo(name="test", base_url="https://api.x.ai/v1", model_name="claude-sonnet-4-5")
    assert detect_provider(info) == "grok"


def test_empty_base_url_treated_as_none():
    """base_url='' should behave like None for default-openai detection."""
    info_empty = ProviderInfo(name="test", base_url="", model_name="gpt-4o-mini")
    info_none = ProviderInfo(name="test", base_url=None, model_name="gpt-4o-mini")
    assert detect_provider(info_empty) == detect_provider(info_none) == "openai"


# ---------- Optional: pytest parametrize for individual case reporting ----------

import pytest  # noqa: E402

@pytest.mark.parametrize(
    "label,base_url,model,expected",
    _DETECT_CASES,
    ids=[c[0] for c in _DETECT_CASES],
)
def test_detect_provider_parametrized(label, base_url, model, expected):
    info = ProviderInfo(name="test", base_url=base_url, model_name=model)
    assert detect_provider(info) == expected


# ---------- Cycle 6: routing dict + 4 new providers ----------

def test_adapters_routing_dict_known_providers():
    """Structural test: _ADAPTERS covers all known providers with correct adapter classes."""
    from universal_llm_adapter import (
        _ADAPTERS, OpenAICompatAdapter, AnthropicAdapter, GoogleAdapter,
    )
    # Native SDK routes
    assert _ADAPTERS["anthropic"] is AnthropicAdapter
    assert _ADAPTERS["google"] is GoogleAdapter
    # OpenAI-compat routes (13 providers via base_url swap)
    for compat_provider in (
        "openai", "groq", "cerebras", "deepseek", "deepinfra", "qwen",
        "local", "grok", "azure", "mistral", "together", "fireworks", "cohere",
    ):
        assert _ADAPTERS[compat_provider] is OpenAICompatAdapter, (
            f"{compat_provider} should route to OpenAICompatAdapter"
        )


def test_adapters_count():
    """_ADAPTERS should have at least 15 entries (13 openai-compat + 2 native)."""
    from universal_llm_adapter import _ADAPTERS
    assert len(_ADAPTERS) >= 15, f"_ADAPTERS has {len(_ADAPTERS)}, expected ≥15"


def test_chat_unknown_provider_raises():
    """chat() should raise NotImplementedError with helpful list for unknown provider."""
    import asyncio
    from universal_llm_adapter import _ADAPTERS

    async def run():
        gen = chat(
            [{"role": "user", "content": "hi"}],
            ProviderInfo(name="t", base_url="https://random.ai/v1", model_name="unknown"),
        )
        try:
            async for _ in gen:
                pass
        except NotImplementedError as e:
            return str(e)
        return None

    err = asyncio.run(run())
    assert err is not None, "expected NotImplementedError for unknown provider"
    assert "not yet supported" in err
    # Should mention at least one known provider in error message
    assert any(p in err for p in _ADAPTERS.keys()), f"error should list known providers: {err}"


# ---------- Mock test for AnthropicAdapter (cycle 6) ----------

@pytest.mark.skipif(
    True,  # skip by default — enable by setting RUN_ADAPTER_MOCK_TESTS=1 once anthropic SDK installed
    reason="anthropic SDK may not be installed; enable manually",
)
def test_anthropic_adapter_routes_text_delta():
    """Mock anthropic SDK: verify AnthropicAdapter yields ResponseWithThought on text_delta."""
    # Note: this test is a skeleton — full mock implementation requires
    # patching anthropic.AsyncAnthropic + its async context manager + async iterator.
    # Defer to integration test (with real API key) when ready.
    pass


@pytest.mark.skipif(
    True,
    reason="google-genai SDK may not be installed",
)
def test_google_adapter_routes_text_chunk():
    """Mock google-genai SDK: verify GoogleAdapter yields ResponseWithThought."""
    pass


if __name__ == "__main__":
    # Allow running without pytest: `python test_universal_adapter.py`
    print("Running tests manually (no pytest needed)...")
    test_detect_provider_all_cases()
    print("  [OK] detect_provider all 15 cases")
    test_response_with_thought_defaults()
    print("  [OK] ResponseWithThought defaults")
    test_response_with_thought_constructed()
    print("  [OK] ResponseWithThought constructed")
    test_response_with_thought_independent_usage_dicts()
    print("  [OK] ResponseWithThought usage dict isolation")
    test_host_takes_precedence_over_model()
    print("  [OK] host > model priority")
    test_empty_base_url_treated_as_none()
    print("  [OK] empty base_url == None")
    print("\n=== 6 manual tests passed ===")
    print("(plus 15 parametrized cases when run via pytest)")
