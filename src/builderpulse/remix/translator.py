"""Translation wrapper using LLM provider."""

from __future__ import annotations
from .summarizer import LLMProvider


class Translator:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def translate(self, text: str, target_lang: str = "zh") -> str:
        system = f"Translate the following text to {target_lang}. Keep technical terms, URLs, and proper nouns in their original language."
        return self.provider.complete(text, system=system)
