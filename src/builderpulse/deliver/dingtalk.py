"""DingTalk delivery channel."""

from __future__ import annotations

from .base import DeliveryChannel


class DingTalkChannel(DeliveryChannel):
    # Plugin Protocol: required class attribute (Task 23).
    name = "dingtalk"
    # P2 fix: explicit per-channel limit. DingTalk text webhook accepts up
    # to ~20KB per message; 20000 chars leaves headroom for sign+headers.
    max_length: int = 20000

    def __init__(self, webhook_url: str = "", **kwargs):
        self.webhook_url = webhook_url

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        import httpx

        if not self.webhook_url:
            raise ValueError("webhook_url required")
        payload = {"msg_type": "text", "content": {"text": content[: self.max_length]}}
        r = httpx.post(self.webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True
