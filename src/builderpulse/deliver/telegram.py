"""Telegram delivery channel."""

from __future__ import annotations

from .base import DeliveryChannel


class TelegramChannel(DeliveryChannel):
    # Plugin Protocol: required class attribute (Task 23).
    name = "telegram"

    def __init__(self, bot_token: str = "", chat_id: str = "", **kwargs):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        import httpx

        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot_token and chat_id required")
        for chunk in self.chunk_content(content):
            r = httpx.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if r.status_code != 200:
                r = httpx.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk},
                    timeout=10,
                )
            r.raise_for_status()
        return True
