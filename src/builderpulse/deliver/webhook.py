"""Generic webhook channel — POST (or other method) JSON content to a URL.

Implements:
- Single HTTP request (any method) with JSON body via ``httpx.request``
- Returns ``True`` on 2xx, ``False`` on 4xx/5xx/exception
- Missing ``url`` is a soft skip: DEBUG log + return False (no raise)

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebhookChannel:
    """Generic HTTP webhook delivery. Sends ``content`` as JSON to a configured URL.

    Satisfies the v2.1.0 ``ChannelPlugin`` Protocol via duck-typing
    (``name`` class attribute + ``deliver`` method). Does not inherit from
    :class:`builderpulse.deliver.base.DeliveryChannel` because that ABC's
    ``send(content, title, content_type)`` signature does not match the
    plugin-style ``deliver(content, **kwargs)`` contract.
    """

    name = "webhook"
    __experimental__ = False

    def __init__(
        self,
        url: str | None = None,
        method: str = "POST",
        headers: dict | None = None,
        **kwargs,
    ):
        self.url = url
        self.method = (method or "POST").upper()
        self.headers = headers or {}

    def deliver(self, content: Any, **kwargs) -> bool:
        if not self.url:
            logger.debug(
                "Webhook channel skipped: url not configured (method=%s)",
                self.method,
            )
            return False
        try:
            resp = httpx.request(
                self.method,
                self.url,
                json=content,
                headers=self.headers,
                timeout=30,
            )
        except Exception as e:
            logger.error("Webhook delivery failed: %s", e)
            return False

        if 200 <= resp.status_code < 300:
            return True

        logger.warning(
            "Webhook %s %s returned %s",
            self.method,
            self.url,
            resp.status_code,
        )
        return False

    def health_check(self) -> bool:
        return self.url is not None
