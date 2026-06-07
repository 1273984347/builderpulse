"""Tests for NotionChannel (v2.1.0 Batch 2, Task 19).

Covers:
- POSTs to https://api.notion.com/v1/pages with correct Bearer + Notion-Version headers
- Body contains parent.database_id and serialized NotionPage properties
- Returns True on 2xx (200, 201)
- Returns False on 4xx/5xx (400, 401, 404, 500)
- Dedup: queries DB first; if a page with the same title exists, no create call is made
- Missing token or database_id → DEBUG log + return False (no raise)
- NotionPage.to_notion_properties() serialization shape

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from builderpulse.deliver.notion import NotionChannel
from builderpulse.deliver.notion_page import NotionPage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def notion():
    return NotionChannel(
        token="ntn_test_token_abc",
        database_id="db_test_123",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_deliver_creates_notion_page(notion):
    """Verify POST to /v1/pages with Bearer + Notion-Version headers + correct body."""
    page = NotionPage(
        title="Test Page",
        tags=["ai", "weekly"],
        url="https://example.com/article",
        published_at="2026-06-07T00:00:00Z",
    )
    with respx.mock() as mock:
        # Mock dedup query (returns empty — no existing page)
        mock.post("https://api.notion.com/v1/databases/db_test_123/query").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        # Mock create page
        mock.post("https://api.notion.com/v1/pages").mock(
            return_value=httpx.Response(
                200, json={"id": "page_123", "url": "https://notion.so/page_123"}
            )
        )
        result = notion.deliver(page)

        assert result is True

        # Find the create call (not the dedup query) — must be inside `with`
        create_calls = [
            c
            for c in mock.calls
            if str(c.request.url).endswith("/v1/pages")
            and "databases" not in str(c.request.url)
        ]
        assert len(create_calls) == 1
        call = create_calls[0]
        assert call.request.method == "POST"
        assert call.request.headers["Authorization"] == "Bearer ntn_test_token_abc"
        assert call.request.headers["Notion-Version"] == "2022-06-28"

        body = json.loads(call.request.content)
        assert body["parent"]["database_id"] == "db_test_123"
        assert body["properties"]["Name"]["title"][0]["text"]["content"] == "Test Page"
        assert body["properties"]["Tags"]["multi_select"] == [
            {"name": "ai"},
            {"name": "weekly"},
        ]
        assert body["properties"]["URL"]["url"] == "https://example.com/article"
        assert (
            body["properties"]["Published"]["date"]["start"] == "2026-06-07T00:00:00Z"
        )


def test_deliver_returns_true_on_2xx(notion):
    """200, 201 return True."""
    for status in [200, 201]:
        with respx.mock() as mock:
            mock.post("https://api.notion.com/v1/databases/db_test_123/query").mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            mock.post("https://api.notion.com/v1/pages").mock(
                return_value=httpx.Response(status, json={"id": "p"})
            )
            assert notion.deliver(NotionPage(title="x")) is True, (
                f"status {status} should return True"
            )


def test_deliver_returns_false_on_4xx_5xx(notion):
    """400, 401, 404, 500 return False."""
    for status in [400, 401, 404, 500]:
        with respx.mock() as mock:
            mock.post("https://api.notion.com/v1/databases/db_test_123/query").mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            mock.post("https://api.notion.com/v1/pages").mock(
                return_value=httpx.Response(status, json={"error": "test"})
            )
            assert notion.deliver(NotionPage(title="x")) is False, (
                f"status {status} should return False"
            )


def test_dedup_skips_creation_when_page_exists(notion):
    """When page with same title already exists in DB, don't create duplicate."""
    with respx.mock() as mock:
        # Mock dedup query — returns existing page with same title
        mock.post("https://api.notion.com/v1/databases/db_test_123/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "existing_123",
                            "properties": {
                                "Name": {"title": [{"text": {"content": "Test Page"}}]}
                            },
                        }
                    ]
                },
            )
        )
        # No /v1/pages call should be made
        result = notion.deliver(NotionPage(title="Test Page"))

        assert result is True  # dedup is a "success" (no duplicate created)
        # Verify NO create call was made
        create_calls = [
            c
            for c in mock.calls
            if str(c.request.url).endswith("/v1/pages")
            and "databases" not in str(c.request.url)
        ]
        assert len(create_calls) == 0, "should not POST /v1/pages when dedup matches"


def test_missing_token_or_db_logs_debug_and_returns_false(caplog):
    """token or database_id missing → DEBUG + False (no raise)."""
    caplog.set_level(logging.DEBUG, logger="builderpulse.deliver.notion")

    # Missing token
    n1 = NotionChannel(token=None, database_id="db")
    assert n1.deliver(NotionPage(title="x")) is False

    # Missing database_id
    n2 = NotionChannel(token="t", database_id=None)
    assert n2.deliver(NotionPage(title="x")) is False

    # Both missing
    n3 = NotionChannel(token=None, database_id=None)
    assert n3.deliver(NotionPage(title="x")) is False

    debug_msgs = [
        r.getMessage().lower() for r in caplog.records if r.levelno == logging.DEBUG
    ]
    # At least one DEBUG message mentions the missing fields
    assert any("token" in m or "database" in m or "db" in m for m in debug_msgs), (
        f"expected DEBUG log about missing fields, got: {debug_msgs}"
    )


def test_notion_page_serialization():
    """NotionPage.to_notion_properties() returns the right Notion API shape."""
    p = NotionPage(
        title="Hello",
        tags=["a", "b"],
        url="https://x",
        published_at="2026-01-01",
    )
    props = p.to_notion_properties()
    assert props["Name"]["title"][0]["text"]["content"] == "Hello"
    assert props["Tags"]["multi_select"] == [{"name": "a"}, {"name": "b"}]
    assert props["URL"]["url"] == "https://x"
    assert props["Published"]["date"]["start"] == "2026-01-01"

    # Empty optional fields
    p2 = NotionPage(title="Just title")
    props2 = p2.to_notion_properties()
    assert props2 == {"Name": {"title": [{"text": {"content": "Just title"}}]}}

    # Extra properties are merged in
    p3 = NotionPage(
        title="With Extras",
        extra={"Status": {"select": {"name": "Published"}}, "Author": "alice"},
    )
    props3 = p3.to_notion_properties()
    assert props3["Status"] == {"select": {"name": "Published"}}
    assert props3["Author"] == "alice"


def test_deliver_accepts_dict_input(notion):
    """deliver() accepts a dict (auto-wraps in NotionPage) and a NotionPage."""
    with respx.mock() as mock:
        mock.post("https://api.notion.com/v1/databases/db_test_123/query").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        mock.post("https://api.notion.com/v1/pages").mock(
            return_value=httpx.Response(200, json={"id": "p"})
        )

        # Dict input
        result = notion.deliver(
            {
                "title": "From Dict",
                "tags": ["test"],
                "url": "https://example.com",
            }
        )
        assert result is True

        create_calls = [
            c
            for c in mock.calls
            if str(c.request.url).endswith("/v1/pages")
            and "databases" not in str(c.request.url)
        ]
        assert len(create_calls) == 1
        body = json.loads(create_calls[0].request.content)
        assert body["properties"]["Name"]["title"][0]["text"]["content"] == "From Dict"
        assert body["properties"]["URL"]["url"] == "https://example.com"
