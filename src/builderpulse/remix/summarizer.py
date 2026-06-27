"""LLM provider abstraction with Map-Reduce for long content."""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("builderpulse.remix")


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self, prompt: str, system: str = "", temperature: float = 0.3
    ) -> str: ...


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        try:
            import openai

            self._client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "openai not installed. Run: pip install builderpulse[llm]"
            )
        self.model = model

    def complete(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "anthropic not installed. Run: pip install builderpulse[llm]"
            )
        self.model = model

    def complete(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def complete(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        import httpx

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        r = httpx.post(f"{self.host}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["response"]


class UniversalAdapterProvider(LLMProvider):
    """Sync wrapper over builderpulse.llm.universal_adapter (15 providers).

    Adds support for any model that the universal adapter detects via
    detect_provider() — Groq, DeepSeek, Mistral, Cohere, Cerebras, Together,
    Fireworks, Qwen, xAI, OpenAI, Anthropic, Google, etc.

    Use prefix `u:` to explicitly select this provider:
        get_provider("u:gpt-4o-mini")           # OpenAI via universal
        get_provider("u:claude-sonnet-4-5")      # Anthropic via universal
        get_provider("u:groq/llama-3.1-70b")     # Groq via universal

    Sync wrapper: blocks on asyncio.run() per call. For high-throughput
    pipelines, use the async universal_adapter.chat() directly.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def complete(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        import asyncio
        import os

        try:
            from builderpulse.llm.universal_adapter import chat, ProviderInfo
        except ImportError as e:
            raise ImportError(
                f"universal_adapter not importable: {e}. "
                "Is builderpulse installed in editable mode? Try: pip install -e ."
            )

        # Fallback chain: explicit api_key → env var → empty
        api_key = (
            self.api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )

        info = ProviderInfo(
            name="auto",
            base_url=self.base_url or os.environ.get("LLM_BASE_URL"),
            api_key=api_key,
            model_name=self.model,
        )

        async def _run():
            chunks = []
            async for chunk in chat(
                messages=[
                    {"role": "system", "content": system or "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                provider_info=info,
                temperature=temperature,
            ):
                if chunk.text:
                    chunks.append(chunk.text)
            return "".join(chunks)

        return asyncio.run(_run())


def get_provider(model: str = "auto", api_key: str | None = None) -> LLMProvider:
    """Auto-detect LLM provider from model name.

    Routing:
    - "u:<model>"  → UniversalAdapterProvider (15 providers via base_url swap)
    - "claude*"    → AnthropicProvider (direct SDK)
    - "gpt*"       → OpenAIProvider (direct SDK)
    - "ollama/*"   → OllamaProvider (local)
    - "auto"       → UniversalAdapterProvider (if installed) → fallback to direct SDK
    - other        → ValueError
    """
    import os

    # Universal adapter prefix: "u:gpt-4o-mini", "u:groq/llama", etc.
    if model.startswith("u:"):
        actual_model = model.split(":", 1)[1]
        return UniversalAdapterProvider(model=actual_model, api_key=api_key)

    if model == "auto":
        # Prefer universal adapter if available (covers 15 providers).
        try:
            import builderpulse.llm.universal_adapter  # noqa: F401
            return UniversalAdapterProvider(model="gpt-4o-mini", api_key=api_key)
        except ImportError:
            pass
        # Fallback to direct SDK providers
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider(api_key=api_key, model="claude-sonnet-4-6")
        elif os.environ.get("OPENAI_API_KEY"):
            return OpenAIProvider(api_key=api_key, model="gpt-4o")
        else:
            return OllamaProvider(model="llama3")

    if model.startswith("claude"):
        return AnthropicProvider(api_key=api_key, model=model)
    elif model.startswith("gpt"):
        return OpenAIProvider(api_key=api_key, model=model)
    elif model.startswith("ollama/"):
        return OllamaProvider(model=model.split("/", 1)[1])
    else:
        raise ValueError(f"Unknown model: {model}. Use claude-* / gpt-* / ollama/* / u:*")


class Summarizer:
    """Summarize content with Map-Reduce for long texts."""

    def __init__(self, provider: LLMProvider, chunk_size: int = 8000):
        self.provider = provider
        self.chunk_size = chunk_size

    def summarize(self, text: str, system: str = "") -> str:
        if len(text) <= self.chunk_size:
            return self.provider.complete(text, system=system)

        # Map-Reduce
        chunks = self._chunk(text)
        summaries = [self.provider.complete(c, system=system) for c in chunks]

        while len(summaries) > 1:
            merged = []
            for i in range(0, len(summaries), 2):
                pair = summaries[i : i + 2]
                merged.append(self.provider.complete("\n\n".join(pair), system=system))
            summaries = merged

        return summaries[0]

    def _chunk(self, text: str) -> list[str]:
        paragraphs = text.split("\n\n")
        chunks, current = [], ""
        for p in paragraphs:
            if len(current) + len(p) > self.chunk_size:
                if current:
                    chunks.append(current)
                current = p
            else:
                current += "\n\n" + p if current else p
        if current:
            chunks.append(current)
        return chunks
