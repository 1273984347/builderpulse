"""Tests for SlackChannel (v2.1.0 Batch 2, Task 18).

Covers:
- POSTs JSON payload to Slack Incoming Webhook URL
- Returns True on Slack's plain-text "ok" response
- Returns False on non-ok body (e.g. "invalid_token", "no_service") and 4xx/5xx
- Custom channel / username / icon_emoji are passed through to payload
- Missing webhook_url → DEBUG log + return False (no raise)
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from builderpulse.deliver.slack import SlackChannel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def slack():
    return SlackChannel(
        webhook_url="https://hooks.slack.com/services/TXXX/BXXX/secret_abc",
        channel="#ai-builders",
        username="BuilderPulse",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_deliver_sends_post_to_slack_webhook(slack):
    """Verify POST to Slack webhook with correct payload structure."""
    with respx.mock() as mock:
        mock.post("https://hooks.slack.com/services/TXXX/BXXX/secret_abc").mock(
            return_value=httpx.Response(200, text="ok")
        )
        result = slack.deliver({"text": "Hello world", "title": "Test"})

        assert result is True
        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert call.request.method == "POST"
        payload = json.loads(call.request.content)
        assert payload["channel"] == "#ai-builders"
        assert payload["username"] == "BuilderPulse"
        # Content should be merged into the text field
        assert "Hello world" in payload["text"] or "Test" in payload["text"]


def test_deliver_returns_true_on_ok_response(slack):
    """Slack returns 'ok' plain text on success."""
    with respx.mock() as mock:
        mock.post("https://hooks.slack.com/services/TXXX/BXXX/secret_abc").mock(
            return_value=httpx.Response(200, text="ok")
        )
        assert slack.deliver({"text": "hi"}) is True


def test_deliver_returns_false_on_error(slack):
    """Non-ok response (4xx, 5xx, or 'invalid_token' body) returns False."""
    # 4xx/5xx with 'invalid_token' body
    for status in [400, 403, 404, 500]:
        with respx.mock() as mock:
            mock.post("https://hooks.slack.com/services/TXXX/BXXX/secret_abc").mock(
                return_value=httpx.Response(status, text="invalid_token")
            )
            assert slack.deliver({"text": "x"}) is False, (
                f"status {status} should return False"
            )

    # 200 with 'no_service' body (Slack-specific error)
    with respx.mock() as mock:
        mock.post("https://hooks.slack.com/services/TXXX/BXXX/secret_abc").mock(
            return_value=httpx.Response(200, text="no_service")
        )
        assert slack.deliver({"text": "x"}) is False


def test_custom_channel_username_emoji():
    """Custom channel, username, icon_emoji passed through to Slack payload."""
    custom = SlackChannel(
        webhook_url="https://hooks.slack.com/services/T0/B0/secret",
        channel="#custom-channel",
        username="CustomBot",
        icon_emoji=":robot_face:",
    )
    with respx.mock() as mock:
        mock.post("https://hooks.slack.com/services/T0/B0/secret").mock(
            return_value=httpx.Response(200, text="ok")
        )
        custom.deliver({"text": "hello"})

        payload = json.loads(mock.calls[0].request.content)
        assert payload["channel"] == "#custom-channel"
        assert payload["username"] == "CustomBot"
        assert payload["icon_emoji"] == ":robot_face:"


def test_missing_webhook_url_logs_debug_and_returns_false(caplog):
    """webhook_url=None → DEBUG + False (no raise)."""
    s = SlackChannel(webhook_url=None, channel="#x")
    caplog.set_level(logging.DEBUG, logger="builderpulse.deliver.slack")
    result = s.deliver({"text": "x"})

    assert result is False
    debug_msgs = [
        r.getMessage().lower() for r in caplog.records if r.levelno == logging.DEBUG
    ]
    assert any(
        "webhook_url" in m and ("missing" in m or "skip" in m or "not" in m)
        for m in debug_msgs
    ), f"expected DEBUG log about missing webhook_url, got: {debug_msgs}"
