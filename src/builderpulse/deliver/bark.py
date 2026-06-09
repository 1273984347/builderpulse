"""Apple Bark channel — push notification via Bark API.

Implements:
- Single HTTP POST to ``{server}/{device_key}/{title}/{body}`` via ``httpx``
- Default server: ``https://api.day.app``
- URL-encodes title and body to handle spaces, slashes, and special chars
- Returns ``True`` on 2xx, ``False`` on 4xx/5xx/exception
- Missing ``device_key`` is a soft skip: DEBUG log + return False (no raise)

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class BarkChannel:
    """Apple Bark push notification. Sends to ``{server}/{device_key}/{title}/{body}``.

    Satisfies the v2.1.0 ``ChannelPlugin`` Protocol via duck-typing
    (``name`` class attribute + ``deliver`` method). Does not inherit from
    :class:`builderpulse.deliver.base.DeliveryChannel` because that ABC's
    ``send(content, title, content_type)`` signature does not match the
    plugin-style ``deliver(content, **kwargs)`` contract.
    """

    name = "bark"
    __experimental__ = False
    DEFAULT_SERVER = "https://api.day.app"

    def __init__(
        self,
        device_key: str | None = None,
        server: str | None = None,
        headers: dict | None = None,
        params: dict | None = None,
        **kwargs,
    ):
        self.device_key = device_key
        self.server = server or self.DEFAULT_SERVER
        self.headers = headers or {}
        self.params = params or {}

    def deliver(self, content: Any, **kwargs) -> bool:
        if not self.device_key:
            logger.debug(
                "Bark channel skipped: device_key not configured (server=%s)",
                self.server,
            )
            return False

        # Extract title and body from content (dict) or use string for body
        if isinstance(content, dict):
            title = str(content.get("title", ""))
            body = str(content.get("body", ""))
        else:
            title = ""
            body = str(content)

        # URL-encode to handle spaces, slashes, special chars
        url = f"{self.server}/{self.device_key}/{quote(title)}/{quote(body)}"

        try:
            resp = httpx.post(
                url,
                headers=self.headers,
                params=self.params,
                timeout=30,
            )
        except Exception as e:
            logger.error("Bark delivery failed: %s", e)
            return False

        if 200 <= resp.status_code < 300:
            return True

        logger.warning(
            "Bark POST %s returned %s: %s",
            url,
            resp.status_code,
            resp.text[:200],
        )
        return False

    def health_check(self) -> bool:
        return self.device_key is not None
