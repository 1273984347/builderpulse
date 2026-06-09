"""Tests for BarkChannel (v2.1.0 Batch 1, Task 16).

Covers:
- Sends POST to {server}/{device_key}/{title}/{body} URL format
- Returns True on 2xx
- Returns False on 4xx/5xx
- Custom server overrides default
- Missing device_key → DEBUG log + return False (no raise)
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from builderpulse.deliver.bark import BarkChannel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bark():
    return BarkChannel(
        device_key="test_device_key_abc",
        server="https://api.day.app",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_deliver_sends_post_to_bark_url(bark):
    """Verify URL format and POST method."""
    with respx.mock() as mock:
        mock.post(
            "https://api.day.app/test_device_key_abc/Test%20Title/Test%20Body"
        ).mock(
            return_value=httpx.Response(200, json={"code": 200, "message": "success"})
        )
        result = bark.deliver({"title": "Test Title", "body": "Test Body"})

        assert result is True
        assert len(mock.calls) == 1
        assert mock.calls[0].request.method == "POST"


def test_deliver_returns_true_on_2xx(bark):
    """200 returns True."""
    with respx.mock() as mock:
        mock.post("https://api.day.app/test_device_key_abc/Hi/Hello").mock(
            return_value=httpx.Response(200, json={"code": 200})
        )
        assert bark.deliver({"title": "Hi", "body": "Hello"}) is True


def test_deliver_returns_false_on_error(bark):
    """4xx/5xx returns False."""
    for status in [400, 500, 503]:
        with respx.mock() as mock:
            mock.post("https://api.day.app/test_device_key_abc/x/y").mock(
                return_value=httpx.Response(status, json={"code": status})
            )
            assert bark.deliver({"title": "x", "body": "y"}) is False, (
                f"status {status} should return False"
            )


def test_custom_server_url():
    """server param overrides default."""
    b = BarkChannel(device_key="k", server="https://my-bark.example.com")
    with respx.mock() as mock:
        mock.post("https://my-bark.example.com/k/Test/Body").mock(
            return_value=httpx.Response(200)
        )
        assert b.deliver({"title": "Test", "body": "Body"}) is True
        # Verify the custom server was used (not the default)
        assert len(mock.calls) == 1
        assert "my-bark.example.com" in str(mock.calls[0].request.url)


def test_missing_device_key_logs_debug_and_returns_false(caplog):
    """device_key=None → DEBUG + False (no raise)."""
    b = BarkChannel(device_key=None, server="https://api.day.app")
    caplog.set_level(logging.DEBUG, logger="builderpulse.deliver.bark")
    result = b.deliver({"title": "x", "body": "y"})

    assert result is False
    debug_msgs = [
        r.getMessage().lower() for r in caplog.records if r.levelno == logging.DEBUG
    ]
    assert any(
        "device_key" in m and ("missing" in m or "skip" in m or "not" in m)
        for m in debug_msgs
    ), f"expected DEBUG log about missing device_key, got: {debug_msgs}"
