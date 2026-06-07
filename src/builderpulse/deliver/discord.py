"""Discord delivery channel."""

from __future__ import annotations

from .base import DeliveryChannel


class DiscordChannel(DeliveryChannel):
    # Plugin Protocol: required class attribute (Task 23).
    name = "discord"

    def __init__(self, webhook_url: str = "", **kwargs):
        self.webhook_url = webhook_url

    @property
    def max_length(self) -> int:
        return 2000  # Discord message limit

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        import httpx

        if not self.webhook_url:
            raise ValueError("webhook_url required")
        # P2 fix: use max_length instead of magic number
        payload = {"content": content[: self.max_length]}
        r = httpx.post(self.webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True
