"""
Tests for universal_llm_adapter — 14 detect_provider cases + ResponseWithThought.

Mirrors the 14 test cases verified in cycle 1 R2 review.
Will be moved to builderpulse/tests/test_llm/ once stable.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from either /tmp (standalone) or builderpulse/tests/ (installed).
# Strategy: detect which mode and import accordingly.
_THIS_DIR = Path(__file__).parent.resolve()
if (_THIS_DIR / "universal_llm_adapter.py").exists():
    # Standalone mode: C:\tmp — adapter alongside test
    sys.path.insert(0, str(_THIS_DIR))
    from universal_llm_adapter import (  # type: ignore[no-redef]
        ProviderInfo,
        ResponseWithThought,
        chat,
        detect_provider,
        merge_provider_defaults,
        truncate_messages,
        get_max_prompt_size,
    )
elif (_THIS_DIR.parent / "src" / "builderpulse" / "llm" / "universal_adapter.py").exists():
    # Installed mode: builderpulse project
    sys.path.insert(0, str(_THIS_DIR.parent / "src"))
    from builderpulse.llm.universal_adapter import (  # type: ignore[no-redef]
        ProviderInfo,
        ResponseWithThought,
        chat,
        detect_provider,
        merge_provider_defaults,
        truncate_messages,
        get_max_prompt_size,
    )
else:
    raise ImportError(
        f"Cannot locate universal_adapter.py. CWD={Path.cwd()}, "
        f"__file__={__file__}, _THIS_DIR={_THIS_DIR}"
    )


def _mod():
    """Return the universal_adapter module regardless of install mode."""
    if "universal_llm_adapter" in sys.modules:
        return sys.modules["universal_lm_adapter"]  # type: ignore[no-redef]
    return sys.modules["builderpulse.llm.universal_adapter"]  # type: ignore[no-redef]


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
    m = _mod()
    # Native SDK routes (cycle 10: +MistralAdapter, +CohereAdapter)
    assert m._ADAPTERS["anthropic"] is m.AnthropicAdapter
    assert m._ADAPTERS["google"] is m.GoogleAdapter
    assert m._ADAPTERS["mistral"] is m.MistralAdapter  # cycle 10: native SDK
    assert m._ADAPTERS["cohere"] is m.CohereAdapter    # cycle 10: native SDK
    # OpenAI-compat routes (11 providers via base_url swap after cycle 10)
    for compat_provider in (
        "openai", "groq", "cerebras", "deepseek", "deepinfra", "qwen",
        "local", "grok", "azure", "together", "fireworks",
    ):
        assert m._ADAPTERS[compat_provider] is m.OpenAICompatAdapter, (
            f"{compat_provider} should route to OpenAICompatAdapter"
        )


def test_adapters_count():
    """_ADAPTERS should have at least 15 entries (11 openai-compat + 4 native)."""
    m = _mod()
    assert len(m._ADAPTERS) >= 15, f"_ADAPTERS has {len(m._ADAPTERS)}, expected ≥15"


def test_cohere_and_mistral_adapters_exist():
    """Cycle 10: native SDK adapter classes are importable."""
    m = _mod()
    assert hasattr(m, "CohereAdapter"), "CohereAdapter class missing"
    assert hasattr(m, "MistralAdapter"), "MistralAdapter class missing"
    # Verify they have the expected interface
    for cls in (m.CohereAdapter, m.MistralAdapter):
        assert hasattr(cls, "stream"), f"{cls.__name__}.stream missing"
        assert hasattr(cls, "__init__"), f"{cls.__name__}.__init__ missing"


def test_chat_unknown_provider_raises():
    """chat() should raise NotImplementedError with helpful list for unknown provider."""
    import asyncio
    m = _mod()

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
    assert any(p in err for p in m._ADAPTERS.keys()), f"error should list known providers: {err}"


# ---------- Mock tests for native SDK adapters ----------
#
# DELETED in first-principles cleanup (cycle 11 → D):
# These 4 tests were `pass` body + `skipif(True)` — pure ceremony, never run.
# When real SDK mocking is needed, add proper tests (not skeleton stubs).
# See CLAUDE.md §0.4 (Complexity Must Be Earned) — skip stubs are technical debt.
#
# Removed:
#   test_anthropic_adapter_routes_text_delta   (cycle 6, skipif=True)
#   test_google_adapter_routes_text_chunk      (cycle 6, skipif=True)
#   test_cohere_adapter_routes_event           (cycle 11, skipif=True)
#   test_mistral_adapter_routes_chunk          (cycle 11, skipif=True)


def test_provider_defaults_no_duplicate():
    """Cycle 11: _PROVIDER_DEFAULT_PARAMS should not have duplicate provider keys."""
    m = _mod()
    keys = list(m._PROVIDER_DEFAULT_PARAMS.keys())
    assert len(keys) == len(set(keys)), f"duplicate keys in _PROVIDER_DEFAULT_PARAMS: {keys}"


def test_truncate_messages_empty_input():
    """Cycle 11: edge case — empty message list returns empty."""
    assert truncate_messages([], max_prompt_size=100, encoder=None) == []


def test_truncate_messages_single_short_message():
    """Cycle 11: single message under limit stays as-is."""
    msgs = [{"role": "user", "content": "hello"}]
    truncated = truncate_messages(msgs, max_prompt_size=1000, encoder=None)
    assert truncated == msgs, f"should not truncate: {truncated}"


def test_merge_provider_defaults_empty_kwargs():
    """Cycle 11: empty kwargs returns just the defaults."""
    merged = merge_provider_defaults("openai", {})
    assert merged == {}, f"openai has no defaults: {merged}"
    merged = merge_provider_defaults("cerebras", {})
    assert merged == {"temperature": 0.7, "max_tokens": 8192}


# ---------- Cycle 8: provider defaults + truncate_messages ----------

def test_provider_defaults_merge_caller_wins():
    """merge_provider_defaults: caller kwargs override provider defaults."""
    # Mistral default: safe_prompt=True
    merged = merge_provider_defaults("mistral", {})
    assert merged == {"safe_prompt": True}, f"unexpected: {merged}"
    # Caller explicitly sets safe_prompt=False → wins
    merged = merge_provider_defaults("mistral", {"safe_prompt": False})
    assert merged["safe_prompt"] is False, "caller should win"
    # Caller adds new key not in defaults → merged in
    merged = merge_provider_defaults("deepseek", {"top_p": 0.95})
    assert merged == {"temperature": 0.6, "top_p": 0.95}, f"unexpected: {merged}"
    # Unknown provider → empty defaults
    merged = merge_provider_defaults("nonexistent", {"x": 1})
    assert merged == {"x": 1}


def test_provider_defaults_all_known_providers():
    """All 15 _ADAPTERS providers should have defaults registered (no KeyError)."""
    m = _mod()
    for provider in m._ADAPTERS:
        assert provider in m._PROVIDER_DEFAULT_PARAMS, (
            f"missing defaults for {provider}"
        )


def test_truncate_messages_preserves_last():
    """truncate_messages should drop oldest first but always keep the last (current question)."""
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    truncated = truncate_messages(msgs, max_prompt_size=10, encoder=None)
    assert len(truncated) >= 1, "should always keep at least the last message"
    assert truncated[-1] == msgs[-1], "last message must be preserved"


def test_truncate_messages_drops_oldest():
    """When total tokens exceed limit, drop oldest messages."""
    # Build 100 large messages
    msgs = [{"role": "user", "content": "X" * 1000} for _ in range(100)]
    truncated = truncate_messages(msgs, max_prompt_size=50, encoder=None)
    # With char heuristic (4 chars/token), 50 tokens ≈ 200 chars
    # Should drop most messages
    assert len(truncated) < len(msgs), f"expected to drop messages, got {len(truncated)}"


def test_truncate_messages_tiktoken_mode():
    """With tiktoken encoder, total tokens after truncation should be ≤ limit."""
    try:
        import tiktoken
    except ImportError:
        pytest.skip("tiktoken not installed")
    enc = tiktoken.get_encoding("cl100k_base")
    msgs = [{"role": "user", "content": "hello world " * 100} for _ in range(50)]  # ~1500 tokens each
    truncated = truncate_messages(msgs, max_prompt_size=1000, encoder=enc)
    total = sum(len(enc.encode(m["content"])) for m in truncated)
    assert total <= 1100, f"truncated total {total} tokens > limit 1000 + tolerance"


def test_get_max_prompt_size_known_and_fallback():
    """get_max_prompt_size returns known limits + 10000 fallback for unknown."""
    assert get_max_prompt_size("gpt-4o") == 60000
    assert get_max_prompt_size("gemini-2.5-flash") == 120000
    assert get_max_prompt_size("claude-opus-4-0") == 60000
    assert get_max_prompt_size("totally-unknown-model") == 10000  # khoj default


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
