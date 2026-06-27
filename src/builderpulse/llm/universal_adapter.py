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
- cache_control / ephemeral prompt caching (Anthropic-specific)
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

@dataclass
class ProviderInfo:
    name: str  # canonical name: openai / anthropic / google / groq / ...
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str = ""


def _host_matches(host: str, *suffixes: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in suffixes)

_HOST_PROVIDERS = (
    (("api.cerebras.ai",), "cerebras"),
    (("api.groq.com",), "groq"),
    (("api.x.ai",), "grok"),
    (("api.deepinfra.com",), "deepinfra"),
    (("api.deepseek.com",), "deepseek"),
    (("dashscope.aliyuncs.com",), "qwen"),
    (("openai.azure.com",), "azure"),
    (("anthropic.com",), "anthropic"),
    (("googleapis.com",), "google"),
    (("api.mistral.ai",), "mistral"),
    (("api.cohere.ai",), "cohere"),
    (("api.together.xyz",), "together"),
    (("api.fireworks.ai",), "fireworks"),
    (("localhost", "127.0.0.1"), "local"),
)

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
    """Return canonical provider name. Khoj's khoj/utils/helpers.py has 8+ such checks."""
    host = urlparse(provider_info.base_url or "").hostname or ""
    for hosts, name in _HOST_PROVIDERS:
        if _host_matches(host, *hosts):
            return name  # type: ignore[return-value]
    for prefixes, name in _MODEL_PROVIDERS:
        if provider_info.model_name.startswith(prefixes):
            return name  # type: ignore[return-value]
    if not provider_info.base_url:
        return "openai"
    return "unknown"


# ---------- Provider-specific default params (Cycle 8) ----------

# Khoj's model_to_prompt_size (conversation/utils.py:61-97) hard-codes per-model limits.
# We add per-PROVIDER defaults that merge into kwargs at chat() time.
# This is a lighter pattern — per-call overrides still win.
_PROVIDER_DEFAULT_PARAMS: dict[str, dict] = {
    "mistral": {"safe_prompt": True},  # Mistral built-in safety layer
    "together": {"safety_model": "default"},
    "fireworks": {"context_length_exceeded_behavior": "error"},
    "deepseek": {"temperature": 0.6},  # DeepSeek recommended default
    "deepinfra": {"temperature": 0.7},
    "cerebras": {"temperature": 0.7, "max_tokens": 8192},
    "groq": {"temperature": 0.7},
    "qwen": {"temperature": 0.7},
    "grok": {"temperature": 0.7},
    "openai": {},  # use caller's defaults
    "anthropic": {},  # native SDK uses different kwargs
    "google": {},  # native SDK uses different kwargs
    "azure": {},  # uses openai's defaults
    "local": {"temperature": 0.7},  # typical for self-hosted
    "cohere": {},
    "fireworks": {"context_length_exceeded_behavior": "error"},
}


def merge_provider_defaults(provider: str, kwargs: dict) -> dict:
    """Merge provider defaults with caller's kwargs. Caller kwargs win (override)."""
    defaults = _PROVIDER_DEFAULT_PARAMS.get(provider, {})
    merged = {**defaults, **kwargs}  # caller wins
    return merged


# ---------- Universal interface ----------

@runtime_checkable
class LLMAdapter(Protocol):
    """Any LLM provider must implement this."""

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]: ...


# ---------- Per-provider adapters ----------

class OpenAICompatAdapter:
    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.info.api_key, base_url=self.info.base_url)
        stream = await client.chat.completions.create(model=model, messages=messages, stream=True, **kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) or ""
            thought = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or ""
            if text or thought:
                yield ResponseWithThought(text=text, thought=thought)


class AnthropicAdapter:
    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=self.info.api_key, base_url=self.info.base_url)
        system_prompt = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt += msg.get("content", "") + "\n"
            else:
                chat_messages.append(msg)
        # Cycle 9 C: prompt caching via cache_control: ephemeral
        # Khoj pattern: anthropic/utils.py:295 (system) + 382 (last message)
        # Reference: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
        if len(chat_messages) > 2 and system_prompt:
            # Cache the system prompt (always re-read, rare to change)
            system_prompt_block = [
                {"type": "text", "text": system_prompt.strip(), "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_prompt_block = system_prompt or None
        # Cache last message (multi-turn conversations benefit most)
        if chat_messages and len(chat_messages) > 2:
            last_msg = chat_messages[-1]
            content = last_msg.get("content", "")
            if isinstance(content, str):
                chat_messages[-1] = {
                    **last_msg,
                    "content": [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ],
                }
        async with client.messages.stream(
            model=model, messages=chat_messages,
            system=system_prompt_block,
            max_tokens=kwargs.pop("max_tokens", 8000), **kwargs,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield ResponseWithThought(text=event.delta.text)
                    elif event.delta.type == "thinking_delta":
                        yield ResponseWithThought(thought=event.delta.thinking)


class GoogleAdapter:
    def __init__(self, provider_info: ProviderInfo):
        self.info = provider_info

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[ResponseWithThought, None]:
        from google import genai
        client = genai.Client(api_key=self.info.api_key)
        contents = [m["content"] for m in messages if m.get("role") == "user"]
        async for chunk in client.aio.models.generate_content_stream(
            model=model, contents=contents, **kwargs,
        ):
            text = getattr(chunk, "text", None)
            if text:
                yield ResponseWithThought(text=text)


# ---------- Routing dict ----------

_ADAPTERS = {
    # OpenAI-compat (13 providers via base_url swap)
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
    "cohere": OpenAICompatAdapter,
    # Native SDK
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
}


# ---------- Caller ----------

async def chat(
    messages: list[dict],
    provider_info: ProviderInfo,
    **kwargs,
) -> AsyncGenerator[ResponseWithThought, None]:
    """Public entry point. Picks the right adapter, merges provider defaults."""
    provider = detect_provider(provider_info)
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        raise NotImplementedError(
            f"Provider {provider} not yet supported. "
            f"Add an adapter class to _ADAPTERS. "
            f"Known providers: {sorted(_ADAPTERS.keys())}"
        )
    # Cycle 8: merge provider defaults (caller wins)
    merged_kwargs = merge_provider_defaults(provider, kwargs)
    adapter = adapter_cls(provider_info)
    async for chunk in adapter.stream(messages, provider_info.model_name, **merged_kwargs):
        yield chunk


# ---------- truncate_messages (Cycle 8: E) ----------

# Khoj pattern: conversation/utils.py:867-946
# Truncates oldest messages until under max_prompt_size, preserves current question.
# We use tiktoken (already in khoj's deps) for token counting.
# Reference: https://github.com/openai/tiktoken

@dataclass
class TruncationConfig:
    """Per-model token limits. Khoj hard-codes 36 models; we provide a sample + caller can extend."""
    model_name: str
    max_prompt_size: int  # tokens
    tokenizer_name: Optional[str] = None  # default: cl100k_base


# Sample limits (mirrors khoj/model_to_prompt_size)
_DEFAULT_MODEL_LIMITS: dict[str, int] = {
    "gpt-4o": 60000,
    "gpt-4o-mini": 60000,
    "gpt-4.1": 60000,
    "gpt-4.1-mini": 120000,
    "o1": 30000,
    "o3": 60000,
    "gemini-2.5-flash": 120000,
    "gemini-2.5-pro": 60000,
    "claude-sonnet-4-0": 60000,
    "claude-opus-4-0": 60000,
}


def get_max_prompt_size(model_name: str) -> int:
    """Return max prompt size for a model. Falls back to 10000 (khoj default)."""
    return _DEFAULT_MODEL_LIMITS.get(model_name, 10000)


def _count_tokens(text: str, encoder) -> int:
    """Count tokens in a string. Khoj uses tiktoken's cl100k_base."""
    if not text:
        return 0
    return len(encoder.encode(text))


def truncate_messages(
    messages: list[dict],
    max_prompt_size: int,
    encoder=None,
) -> list[dict]:
    """Drop oldest messages until under max_prompt_size. Preserves the last message
    (the current user question — critical for khoj's truncate semantics).

    Args:
        messages: list of {role, content} dicts (OpenAI chat format)
        max_prompt_size: token limit
        encoder: tiktoken Encoding (lazy import to avoid hard dep)

    Returns: truncated messages list
    """
    if encoder is None:
        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            # Fallback: estimate 4 chars per token (rough heuristic)
            return _truncate_by_chars(messages, max_prompt_size * 4)

    def total_tokens() -> int:
        return sum(_count_tokens(m.get("content", ""), encoder) for m in messages)

    # Khoj pattern: drop oldest first while preserving the last message
    # Reference: conversation/utils.py:891-907
    msgs = list(messages)  # don't mutate input
    while len(msgs) > 1 and total_tokens() > max_prompt_size:
        msgs.pop(0)  # drop oldest

    # If single message still over limit, truncate content
    if msgs and total_tokens() > max_prompt_size:
        last = msgs[-1]
        content = last.get("content", "")
        tokens = encoder.encode(content)
        # Reserve space for the question's last ~100 tokens (khoj pattern: line 925)
        keep_tokens = tokens[-100:] if len(tokens) > 100 else []
        truncated = encoder.decode(tokens[: max(0, max_prompt_size - len(keep_tokens))])
        if keep_tokens:
            truncated += encoder.decode(keep_tokens)
        msgs = [{**last, "content": truncated}]

    return msgs


def _truncate_by_chars(messages: list[dict], max_chars: int) -> list[dict]:
    """Fallback truncation when tiktoken unavailable. Rough char-based heuristic."""
    msgs = list(messages)
    total = sum(len(m.get("content", "")) for m in msgs)
    while len(msgs) > 1 and total > max_chars:
        msgs.pop(0)
        total = sum(len(m.get("content", "")) for m in msgs)
    return msgs


# ---------- Example usage ----------

async def example():
    """How you'd call this from builderpulse:
    ```python
    async for chunk in chat(
        messages=[{"role": "user", "content": "Hello"}],
        provider_info=ProviderInfo(name="auto", base_url=None, api_key="sk-...",
                                  model_name="gpt-4o-mini"),
    ):
        if chunk.text: print(chunk.text, end="", flush=True)
        if chunk.thought: print(f"[think: {chunk.thought}]", end="", flush=True)
    ```
    """
    pass


# ---------- What khoj does that you DON'T need to copy ----------

# 1. tenacity @retry decorators — add later if you need it
# 2. cache_control: ephemeral prompt caching — Anthropic-specific optimization
# 3. clean_response_schema for strict JSON — only if you use tool calling
# 4. model_to_prompt_size hard-coded 36-model dict — copy when shipping, update quarterly
# 5. commit_conversation_trace (git-as-DB) — only if you want session replay
