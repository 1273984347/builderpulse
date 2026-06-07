"""Tests for WebhookChannel (v2.1.0 Batch 1, Task 15).

Covers:
- Sends POST request with JSON body
- Returns True on 2xx (200, 201, 202, 204)
- Returns False on 4xx/5xx (400, 401, 404, 500, 502, 503)
- Custom method (PUT) and headers are forwarded
- Missing url → DEBUG log + return False (no raise)
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from builderpulse.deliver.webhook import WebhookChannel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def webhook():
    return WebhookChannel(
        url="https://example.com/webhook",
        method="POST",
        headers={"X-Custom": "test"},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_deliver_sends_post_request(webhook):
    """Verify URL is called with method=POST, JSON body=content."""
    with respx.mock() as mock:
        route = mock.post("https://example.com/webhook").mock(
            return_value=httpx.Response(200, text="ok")
        )
        result = webhook.deliver({"message": "hello", "items": [1, 2, 3]})

        assert result is True
        assert route.called
        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert call.request.method == "POST"
        sent_body = json.loads(call.request.content)
        assert sent_body == {"message": "hello", "items": [1, 2, 3]}


def test_deliver_returns_true_on_2xx(webhook):
    """200, 201, 202, 204 all return True."""
    for status in [200, 201, 202, 204]:
        with respx.mock() as mock:
            mock.post("https://example.com/webhook").mock(
                return_value=httpx.Response(status)
            )
            assert webhook.deliver({"x": 1}) is True, f"status {status} should return True"


def test_deliver_returns_false_on_4xx_5xx(webhook):
    """400, 401, 404, 500, 502, 503 return False."""
    for status in [400, 401, 404, 500, 502, 503]:
        with respx.mock() as mock:
            mock.post("https://example.com/webhook").mock(
                return_value=httpx.Response(status)
            )
            assert webhook.deliver({"x": 1}) is False, f"status {status} should return False"


def test_custom_method_and_headers():
    """Custom method (PUT) and headers are sent."""
    wh = WebhookChannel(
        url="https://example.com/hook",
        method="PUT",
        headers={"Authorization": "Bearer test-token", "X-Custom": "value"},
    )
    with respx.mock() as mock:
        mock.put("https://example.com/hook").mock(return_value=httpx.Response(200))
        result = wh.deliver({"data": 1})

        assert result is True
        assert len(mock.calls) == 1
        req = mock.calls[0].request
        assert req.method == "PUT"
        assert req.headers["Authorization"] == "Bearer test-token"
        assert req.headers["X-Custom"] == "value"


def test_missing_url_logs_debug_and_returns_false(caplog):
    """url=None → DEBUG log + return False (no raise)."""
    wh = WebhookChannel(url=None, method="POST")
    caplog.set_level(logging.DEBUG, logger="builderpulse.deliver.webhook")
    result = wh.deliver({"x": 1})

    assert result is False
    # Verify a debug record was emitted that mentions the missing url
    debug_msgs = [r.getMessage().lower() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(
        "url" in m and ("missing" in m or "skip" in m or "not" in m)
        for m in debug_msgs
    ), f"expected DEBUG log about missing url, got: {debug_msgs}"
