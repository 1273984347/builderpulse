"""Slack channel — Incoming Webhook delivery.

Implements:
- Single HTTP POST to a Slack Incoming Webhook URL with JSON payload
- Payload supports: ``text`` (required), ``channel``, ``username``,
  ``icon_emoji``, ``icon_url``, ``blocks``
- Slack returns plain text ``"ok"`` (200) on success and plain text
  error codes such as ``"invalid_token"``, ``"no_service"``,
  ``"channel_not_found"`` on failure.
- Returns ``True`` on Slack's ``"ok"`` response, ``False`` on any other
  body or 4xx/5xx status.
- Missing ``webhook_url`` is a soft skip: DEBUG log + return False (no raise).

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SlackChannel:
    """Delivers content to Slack via an Incoming Webhook URL.

    Slack's incoming webhooks accept a JSON payload with ``text`` and optional
    ``channel``, ``username``, ``icon_emoji`` / ``icon_url``, ``blocks``. On
    success Slack returns plain text ``"ok"``; on failure it returns plain text
    error codes (``"invalid_token"``, ``"no_service"``, ``"channel_not_found"``).

    Satisfies the v2.1.0 ``ChannelPlugin`` Protocol via duck-typing
    (``name`` class attribute + ``deliver`` method). Does not inherit from
    :class:`builderpulse.deliver.base.DeliveryChannel` because that ABC's
    ``send(content, title, content_type)`` signature does not match the
    plugin-style ``deliver(content, **kwargs)`` contract.
    """

    name = "slack"
    __experimental__ = False

    def __init__(
        self,
        webhook_url: str | None = None,
        channel: str = "#general",
        username: str | None = None,
        icon_emoji: str | None = None,
        icon_url: str | None = None,
        **kwargs,
    ):
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self.icon_url = icon_url

    def deliver(self, content: Any, **kwargs) -> bool:
        if not self.webhook_url:
            logger.debug(
                "Slack channel skipped: webhook_url not configured (channel=%s)",
                self.channel,
            )
            return False

        # Build Slack payload — channel is the only required override field
        payload: dict = {"channel": self.channel}
        if self.username:
            payload["username"] = self.username
        if self.icon_emoji:
            payload["icon_emoji"] = self.icon_emoji
        if self.icon_url:
            payload["icon_url"] = self.icon_url

        # Extract text (and optional blocks) from content
        if isinstance(content, dict):
            text = str(content.get("text", ""))
            if "blocks" in content:
                payload["blocks"] = content["blocks"]
        else:
            text = str(content)
        payload["text"] = text

        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=30)
        except Exception as e:
            logger.error("Slack delivery failed: %s", e)
            return False

        # Slack returns plain text "ok" on success — anything else is failure
        if resp.status_code == 200 and resp.text.strip() == "ok":
            return True

        logger.warning(
            "Slack webhook returned %s: %s",
            resp.status_code,
            resp.text[:200],
        )
        return False

    def health_check(self) -> bool:
        return self.webhook_url is not None
