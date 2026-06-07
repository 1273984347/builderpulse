"""WeCom (Enterprise WeChat) delivery channel."""

from __future__ import annotations

from .base import DeliveryChannel


class WeComChannel(DeliveryChannel):
    # Plugin Protocol: required class attribute (Task 23).
    name = "wecom"

    def __init__(self, webhook_url: str = "", **kwargs):
        self.webhook_url = webhook_url

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        import httpx

        if not self.webhook_url:
            raise ValueError("webhook_url required")
        payload = {"msgtype": "text", "text": {"content": content[: self.max_length]}}
        r = httpx.post(self.webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True
