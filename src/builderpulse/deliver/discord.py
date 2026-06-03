"""Discord delivery channel."""
from __future__ import annotations

from .base import DeliveryChannel


class DiscordChannel(DeliveryChannel):
    def __init__(self, webhook_url: str = "", **kwargs):
        self.webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        import httpx

        if not self.webhook_url:
            raise ValueError("webhook_url required")
        payload = {"content": content[:2000]}
        r = httpx.post(self.webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True
