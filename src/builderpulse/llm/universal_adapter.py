"""
Universal LLM Adapter — extracted from khoj-ai/khoj (AGPL-3.0).

Source: khoj/src/khoj/processor/conversation/openai/utils.py (1314 lines, R4 deep read).
Pattern: 10+ LLM providers (OpenAI / Anthropic / Google / X.AI Grok / DeepSeek / Qwen /
Cerebras / Groq / Azure / DeepInfra / vLLM / sgLang) through ONE async streaming
interface. The trick: every provider eventually yields chunks with `text_delta` and
`thought_delta` events. We wrap them in a single ResponseWithThought dataclass and
let the caller ignore which provider produced them.

Why extract this:
- builderpulse (your副业) needs multi-LLM support without rewriting adapters
- 5+ LLM providers are now standard, vendor lock-in is the worst kind of debt
- Khoj is AGPL — can't import directly, but the pattern is yours to take

What this skeleton does NOT include (intentionally):
- retry/timeout/backoff (khoj uses tenacity, add later)
- cache_control / prompt caching (Anthropic-specific)
- image / multimodal (separate concern)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Literal, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse


# ---------- Data model ----------

@dataclass
class ResponseWithThought:
    """A single chunk yielded by any LLM provider, normalized.

    Khoj's chat_view.ts renders `thought` as italic markdown above `text`. The
    dataclass lets the frontend ignore which provider produced the chunk.
    """
    text: str = ""
    thought: str = ""
    raw_content: Optional[list] = None
    usage: dict = field(default_factory=dict)


class StreamEventType(str, Enum):
    """Event types in the streaming protocol."""
    TEXT_DELTA = "text_delta"
    THOUGHT_DELTA = "thought_delta"
    DONE = "done"
    ERROR = "error"


# ---------- Provider detection ----------

# Khoj's khoj.utils.helpers has is_openai_api / is_local_api / is_cerebras_api etc.
# The detection pattern: hostname string match OR model_name prefix match.
# e.g. api_base_url.startswith("https://api.cerebras.ai/v1") → cerebras

@dataclass
class ProviderInfo:
    name: str  # canonical name: openai / anthropic / google / groq / ...
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str = ""


# Hostname → provider mapping (khoj uses .startswith on full URL; we use
# urlparse + endswith for subdomain support, e.g. my-resource.openai.azure.com)
def _host_matches(host: str, *suffixes: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)

_HOST_PROVIDERS = (
    (("api.cerebras.ai",), "cerebras"),
    (("api.groq.com",), "groq"),
    (("api.x.ai",), "grok"),
    (("api.deepinfra.com",), "deepinfra"),
    (("api.deepseek.com",), "deepseek"),
    (("dashscope.aliyuncs.com",), "qwen"),
    (("openai.azure.com",), "azure"),  # Azure OpenAI deployments
    (("anthropic.com",), "anthropic"),  # api.anthropic.com direct
    (("googleapis.com",), "google"),    # generativelanguage.googleapis.com
    # Cycle 6 add: 4 more providers that share OpenAI-compat or have native SDKs
    (("api.mistral.ai",), "mistral"),         # OpenAI-compat
    (("api.cohere.ai",), "cohere"),           # has native SDK but we route to OpenAI-compat (Cohere also exposes compat endpoint)
    (("api.together.xyz",), "together"),      # OpenAI-compat
    (("api.fireworks.ai",), "fireworks"),     # OpenAI-compat
    (("localhost", "127.0.0.1"), "local"),
)

# Model-name prefix → provider mapping (used when hostname is generic,
# e.g. when proxying OpenAI-compatible APIs)
_MODEL_PROVIDERS = (
    (("claude-", "claude_"), "anthropic"),
    (("gemini-", "gemma-", "palm-"), "google"),
    (("grok-",), "grok"),
    (("qwen", "qwq"), "qwen"),
    (("deepseek-",), "deepseek"),
    (("minimax-m", "kimi-"), "unknown"),  # known but no adapter yet
)


def detect_provider(provider_info: ProviderInfo) -> Literal[
    "openai", "anthropic", "google", "grok", "deepseek",
    "qwen", "cerebras", "groq", "azure", "deepinfra",
    "mistral", "cohere", "together", "fireworks",
    "local", "unknown"
]:
    """Return canonical provider name. Khoj's khoj/utils/helpers.py has 8+ such checks.

    Reference: khoj/utils/helpers.py is_openai_api() + is_local_api() + is_cerebras_api() + is_groq_api()
    See khoj/processor/conversation/openai/utils.py:859-942 for the full pattern.
    """
    host = urlparse(provider_info.base_url or "").hostname or ""
    for hosts, name in _HOST_PROVIDERS:
        if _host_matches(host, *hosts):
            return name  # type: ignore[return-value]
    for prefixes, name in _MODEL_PROVIDERS:
        if provider_info.model_name.startswith(prefixes):
            return name  # type: ignore[return-value]
    # base_url is None OR empty + no model match → default to official OpenAI (khoj pattern).
    # Use `not` not `is None` so empty string also routes to openai (common API key omission).
    if not provider_info.base_url:
        return "openai"
    return "unknown"


# ---------- Universal interface ----------

@runtime_checkable
class LLMAdapter(Protocol):
    """Any LLM provider must implement this. Khoj uses 3 implementations:

    - openai/utils.py (handles Chat Completions + Responses API + most providers)
    - anthropic/utils.py (Claude-specific: thinking blocks + prompt caching)
    - google/utils.py (Gemini-specific: genai SDK)

    Each one normalizes to ResponseWithThought — that's the whole point.
    """

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        """Yield ResponseWithThought chunks. Implementations handle:

        - Khoj pattern: tenacity @retry wraps the inner client call
        - Local models: 300s read timeout; remote: 60s
        - Reasoning models: route thought_delta to `thought` field
        - Tool calls: yield as JSON in `text` (khoj pattern)
        """
        ...


# ---------- Per-provider adapters ----------

class OpenAICompatAdapter:
    """The khoj universal pattern: OpenAI-compatible API surface covers ~10 providers.

    All of these use the same httpx-based OpenAI client, just with different
    base_url. Khoj's openai/utils.py:1-100 lines handle Chat Completions API
    + Responses API + reasoning + thought streaming in ONE function.
    """

    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        # TODO #2 (DONE): OpenAI AsyncClient + stream + yield chunks.
        # Reference: khoj/processor/conversation/openai/utils.py:287-437
        # (chat_completion_with_backoff async generator, ~150 lines condensed to ~10)
        from openai import AsyncOpenAI  # local import: openai is a hard dep at call site
        client = AsyncOpenAI(api_key=self.info.api_key, base_url=self.info.base_url)
        stream = await client.chat.completions.create(model=model, messages=messages, stream=True, **kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Reasoning content field: DeepSeek / vLLM use `reasoning_content`,
            # OpenAI gpt-oss uses `reasoning`. Khoj pattern: route both → thought.
            text = getattr(delta, "content", None) or ""
            thought = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or ""
            if text or thought:
                yield ResponseWithThought(text=text, thought=thought)


class AnthropicAdapter:
    """Anthropic Claude direct adapter (uses anthropic SDK, not OpenAI-compat).

    Khoj's anthropic/utils.py:184-277 does this with extra features:
    - extended thinking (line 102-109)
    - prompt caching via cache_control: ephemeral (line 295, 382)
    - tool_choice: auto + cache tool defs (line 86-87)
    - JSON prefill trick (line 96)
    """

    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        from anthropic import AsyncAnthropic  # local import: optional dep
        client = AsyncAnthropic(api_key=self.info.api_key, base_url=self.info.base_url)
        # Anthropic API requires system prompt separate from messages.
        # Extract system message if present (khoj pattern: anthropic/utils.py:280-298)
        system_prompt = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt += msg.get("content", "") + "\n"
            else:
                chat_messages.append(msg)
        async with client.messages.stream(
            model=model,
            messages=chat_messages,
            system=system_prompt or None,
            max_tokens=kwargs.pop("max_tokens", 8000),
            **kwargs,
        ) as stream:
            async for event in stream:
                # Khoj pattern: anthropic/utils.py:244-253 — route text_delta/thinking_delta
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield ResponseWithThought(text=event.delta.text)
                    elif event.delta.type == "thinking_delta":
                        yield ResponseWithThought(thought=event.delta.thinking)


class GoogleAdapter:
    """Google Gemini direct adapter (uses google-genai SDK).

    Khoj's google/utils.py is similar in structure. The genai SDK has its own
    streaming API that differs from OpenAI: each chunk has .text or .parts,
    not a delta.content.
    """

    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        from google import genai  # local import: optional dep
        client = genai.Client(api_key=self.info.api_key)
        # Convert messages to genai format (simplified — khoj handles more cases)
        contents = [m["content"] for m in messages if m.get("role") == "user"]
        async for chunk in client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            **kwargs,
        ):
            # genai SDK: chunk.text is the text delta
            text = getattr(chunk, "text", None)
            if text:
                yield ResponseWithThought(text=text)


# ---------- Caller: pick adapter by provider ----------

# TODO #3 (DONE): routing dict — map canonical provider → adapter class.
# OpenAI-compat covers ~8 providers via base_url swap; Anthropic + Google need
# their own SDKs because their protocol differs from OpenAI's.
_ADAPTERS = {
    # OpenAI-compat (covers via base_url swap) — 13 providers
    "openai": OpenAICompatAdapter,
    "groq": OpenAICompatAdapter,
    "cerebras": OpenAICompatAdapter,
    "deepseek": OpenAICompatAdapter,
    "deepinfra": OpenAICompatAdapter,
    "qwen": OpenAICompatAdapter,
    "local": OpenAICompatAdapter,
    "grok": OpenAICompatAdapter,
    "azure": OpenAICompatAdapter,
    "mistral": OpenAICompatAdapter,
    "together": OpenAICompatAdapter,
    "fireworks": OpenAICompatAdapter,
    # Native SDK (different protocol from OpenAI)
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
    # Cohere: their /v1/chat is OpenAI-compat-ish but we'll skip — register as compat
    # for now; production should use their native SDK for best feature parity.
    "cohere": OpenAICompatAdapter,
    # TODO: add reka, jina, hyperbolic
}


async def chat(
    messages: list[dict],
    provider_info: ProviderInfo,
    **kwargs,
) -> AsyncGenerator[ResponseWithThought, None]:
    """Public entry point. Picks the right adapter based on detect_provider()."""
    provider = detect_provider(provider_info)
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        raise NotImplementedError(
            f"Provider {provider} not yet supported. "
            f"Add an adapter class to _ADAPTERS in universal_adapter.py. "
            f"Known providers: {sorted(_ADAPTERS.keys())}"
        )
    adapter = adapter_cls(provider_info)
    async for chunk in adapter.stream(messages, provider_info.model_name, **kwargs):
        yield chunk


# ---------- Example usage ----------

async def example():
    """How you'd call this from builderpulse:

    ```python
    async for chunk in chat(
        messages=[{"role": "user", "content": "Hello"}],
        provider_info=ProviderInfo(
            name="auto",
            base_url=None,  # None = official OpenAI
            api_key="sk-...",
            model_name="gpt-4o-mini",
        ),
    ):
        if chunk.text:
            print(chunk.text, end="", flush=True)
        if chunk.thought:
            print(f"[think: {chunk.thought}]", end="", flush=True)
    ```
    """
    pass


# ---------- What khoj does that you DON'T need to copy ----------

# 1. tenacity @retry decorators everywhere (lines 83-94, 275-286, 439-450, 558-569)
#    → add later if you need it; skip for v1
# 2. cache_control: ephemeral for prompt caching (anthropic/utils.py:295, 382)
#    → Anthropic-only optimization, add when you actually pay per token
# 3. clean_response_schema for strict JSON output (openai/utils.py:1290-1314)
#    → needed only if you use tool calling
# 4. truncate_messages token-aware (conversation/utils.py:867-946)
#    → important but separate concern; add a tokenizer dep later
# 5. model_to_prompt_size hard-coded dict (conversation/utils.py:61-97)
#    → copy the 36-model dict when you ship; update quarterly
