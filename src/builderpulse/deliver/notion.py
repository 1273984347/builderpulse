"""Notion Database channel — create pages in a Notion database via Internal Integration Token.

Implements:
- Two HTTP calls per delivery:
    1. ``POST /v1/databases/{database_id}/query`` to look up an existing
       page with the same title (dedup — see spec §3.2).
    2. ``POST /v1/pages`` to create a new page with the serialized
       properties (see :mod:`builderpulse.deliver.notion_page`).
- Auth: Internal Integration Token (Bearer). No OAuth, no callback server.
- Required headers: ``Authorization: Bearer <token>`` + ``Notion-Version: 2022-06-28``.
- Returns ``True`` on 2xx create or when dedup finds a match.
- Missing ``token`` or ``database_id`` is a soft skip: DEBUG log + return False
  (no raise).

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2 + §9.3 I
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .notion_page import NotionPage

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionChannel:
    """Delivers content as pages in a Notion database.

    Satisfies the v2.1.0 ``ChannelPlugin`` Protocol via duck-typing
    (``name`` class attribute + ``deliver`` method). Does not inherit
    from :class:`builderpulse.deliver.base.DeliveryChannel` because that
    ABC's ``send(content, title, content_type)`` signature does not
    match the plugin-style ``deliver(content, **kwargs)`` contract.
    """

    name = "notion"
    __experimental__ = False

    def __init__(
        self,
        token: str | None = None,
        database_id: str | None = None,
        **kwargs,
    ):
        self.token = token
        self.database_id = database_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def deliver(self, content: Any, **kwargs) -> bool:
        if not self.token or not self.database_id:
            missing = []
            if not self.token:
                missing.append("token")
            if not self.database_id:
                missing.append("database_id")
            logger.debug(
                "Notion channel skipped: missing %s",
                ", ".join(missing),
            )
            return False

        # Normalise content to a NotionPage
        if isinstance(content, NotionPage):
            page = content
        elif isinstance(content, dict):
            page = NotionPage(
                title=content.get("title", "Untitled"),
                tags=content.get("tags", []) or [],
                url=content.get("url"),
                published_at=content.get("published_at"),
                extra=content.get("extra", {}) or {},
            )
        else:
            page = NotionPage(title=str(content))

        try:
            # Step 1: dedup query — does a page with the same title exist?
            query_resp = httpx.post(
                f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                headers=self._headers(),
                json={
                    "filter": {
                        "property": "Name",
                        "title": {"equals": page.title},
                    }
                },
                timeout=30,
            )
            if query_resp.status_code == 200:
                results = query_resp.json().get("results") or []
                if results:
                    logger.debug(
                        "Notion: page '%s' already exists, skipping (dedup)",
                        page.title,
                    )
                    return True  # dedup is a "success" — no duplicate created

            # Step 2: create the page
            body = {
                "parent": {"database_id": self.database_id},
                "properties": page.to_notion_properties(),
            }
            create_resp = httpx.post(
                f"{NOTION_API_BASE}/pages",
                headers=self._headers(),
                json=body,
                timeout=30,
            )
        except Exception as e:
            logger.error("Notion delivery failed: %s", e)
            return False

        if 200 <= create_resp.status_code < 300:
            return True
        logger.warning(
            "Notion create returned %s: %s",
            create_resp.status_code,
            create_resp.text[:200],
        )
        return False

    def health_check(self) -> bool:
        """Return True if both token and database_id are configured.

        This is a cheap configuration probe; it does NOT hit the Notion API
        (avoid spurious WARNs in ``bp config show`` when credentials are blank).
        """
        return self.token is not None and self.database_id is not None
