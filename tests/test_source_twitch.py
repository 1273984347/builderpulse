"""Tests for TwitchSource (v2.1.0 Batch 1, Task 14).

Covers:
- channel_logins normalized to lowercase
- Get Videos uses user_id (numeric) — never login/display_name
- 401 response triggers token refresh + retry once
- Token cache is thread-safe (no thundering herd on concurrent 401)
- Missing-credential behavior: DEBUG log + skip (no raise, no block)
- Log sanitization: client_secret never appears in logs
"""
from __future__ import annotations

import logging
import threading
import time

import httpx
import pytest
import respx

from builderpulse.sources.twitch import TwitchAuth, TwitchSource, _token_cache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def twitch_source():
    return TwitchSource(
        client_id="test_client_id",
        client_secret="test_client_secret",
        channel_logins=["Anthropic", "OPENAI"],
        rate_limit_points_per_minute=800,
    )


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Reset module-level token cache between tests to prevent leakage."""
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0.0
    yield
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0.0


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_channel_logins_normalized_to_lowercase():
    """Config stores logins in lowercase; lookup is case-insensitive."""
    src = TwitchSource(
        client_id="x", client_secret="y", channel_logins=["Anthropic", "OPENAI", "MixedCase"]
    )
    assert src.channel_logins == ["anthropic", "openai", "mixedcase"]


def test_fetch_uses_user_id_not_login(twitch_source):
    """After Get Users, use the returned numeric id (NOT login/display_name)
    when calling Get Videos."""
    token_payload = {"access_token": "test_token", "expires_in": 5184000}
    # Get Users returns id="12345" for login "anthropic"
    users_payload = {
        "data": [
            {"id": "12345", "login": "anthropic", "display_name": "Anthropic"},
        ]
    }
    videos_payload = {
        "data": [
            {
                "id": "v1",
                "url": "https://twitch.tv/videos/v1",
                "title": "VOD 1",
                "published_at": "2026-06-01T00:00:00Z",
                "user_id": "12345",
                "user_login": "anthropic",
            }
        ]
    }

    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=token_payload)
        )
        mock.get("https://api.twitch.tv/helix/users").mock(
            return_value=httpx.Response(200, json=users_payload)
        )
        mock.get("https://api.twitch.tv/helix/videos").mock(
            return_value=httpx.Response(200, json=videos_payload)
        )

        items = twitch_source.fetch()

        # Get Videos must be called with user_id=12345 (numeric id from Get Users),
        # NOT with login=anthropic
        videos_call = next(c for c in mock.calls if "helix/videos" in str(c.request.url))
        url_str = str(videos_call.request.url)
        assert "user_id=12345" in url_str
        # Should NOT include login=anthropic in the videos URL
        assert "login=anthropic" not in url_str

    # Result list should contain exactly the one VOD
    assert len(items) == 1
    assert items[0]["url"] == "https://twitch.tv/videos/v1"
    assert items[0]["title"] == "VOD 1"
    assert items[0]["source"] == "twitch"


def test_token_refresh_on_401(twitch_source):
    """When Get Users returns 401, refresh the token and retry once."""
    token_payload = {"access_token": "fresh_token", "expires_in": 5184000}
    users_unauthorized = httpx.Response(401, json={"error": "Unauthorized"})
    users_success = httpx.Response(200, json={"data": [{"id": "12345", "login": "anthropic"}]})
    videos_ok = httpx.Response(200, json={"data": []})

    with respx.mock(assert_all_called=False) as mock:
        # Both token calls (initial + refresh) return the same payload
        mock.post("https://id.twitch.tv/oauth2/token").mock(
            return_value=httpx.Response(200, json=token_payload)
        )
        # Get Users: first call 401, second call 200 (after refresh)
        mock.get("https://api.twitch.tv/helix/users").mock(
            side_effect=[
                users_unauthorized,
                users_success,
            ]
        )
        mock.get("https://api.twitch.tv/helix/videos").mock(
            return_value=videos_ok
        )

        # Must not raise — 401 → refresh + retry
        items = twitch_source.fetch()

        # Should have made >= 2 token requests (initial + at least one refresh)
        token_calls = [c for c in mock.calls if "oauth2/token" in str(c.request.url)]
        assert len(token_calls) >= 2, (
            f"Expected initial + refresh token calls, got {len(token_calls)}"
        )
        # Should have called Get Users twice (401 then 200)
        users_calls = [c for c in mock.calls if "helix/users" in str(c.request.url)]
        assert len(users_calls) == 2, f"Expected 2 Get Users calls, got {len(users_calls)}"

    # Should not raise
    assert items is not None


def test_token_cache_thread_safety():
    """Multiple threads concurrently triggering 401 → only one token refresh.

    The threading.Lock in TwitchAuth._token_cache must serialize refresh,
    so other threads block on the lock and reuse the newly-fetched token
    instead of each issuing their own refresh (thundering-herd prevention).
    """
    refresh_count = [0]
    refresh_lock = threading.Lock()

    def slow_token_response(*_args, **_kwargs):
        with refresh_lock:
            refresh_count[0] += 1
        time.sleep(0.1)  # simulate network latency
        return httpx.Response(200, json={"access_token": "new_token", "expires_in": 5184000})

    # Each thread: fetch() may call Get Users up to 2 times (initial 401 + retry)
    # so provide enough 401s for 5 threads × 2 attempts = 10, plus a final OK.
    users_401 = httpx.Response(401, json={"error": "Unauthorized"})
    users_ok = httpx.Response(200, json={"data": [{"id": "1", "login": "x"}]})
    videos_ok = httpx.Response(200, json={"data": []})

    # 5 threads × max 2 Get Users calls = 10. Provide 15 401s + 1 OK for safety.
    side_effects = [users_401] * 15 + [users_ok]

    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://id.twitch.tv/oauth2/token").mock(side_effect=slow_token_response)
        mock.get("https://api.twitch.tv/helix/users").mock(side_effect=side_effects)
        mock.get("https://api.twitch.tv/helix/videos").mock(return_value=videos_ok)

        src = TwitchSource(client_id="x", client_secret="y", channel_logins=["x"])
        threads = [threading.Thread(target=src.fetch) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # Only one initial refresh + (at most) one retry refresh should have happened.
    # With the lock, all 5 threads share the same refresh result.
    assert refresh_count[0] <= 2, (
        f"Expected <= 2 token refreshes (initial + 1 retry), got {refresh_count[0]}. "
        "Lock may not be preventing thundering herd."
    )


def test_missing_credentials_log_debug_and_skip(caplog):
    """When client_id OR client_secret is absent, log DEBUG and skip — no raise, no block."""
    src = TwitchSource(
        client_id=None, client_secret="y", channel_logins=["anthropic"]
    )
    caplog.set_level(logging.DEBUG, logger="builderpulse.sources.twitch")

    # Must not raise
    items = src.fetch()

    # Must return empty list (skip the source, do not block)
    assert items == []

    # Must have logged a DEBUG message about missing credentials
    assert any(
        "missing" in r.getMessage().lower() or "credential" in r.getMessage().lower()
        for r in caplog.records
    ), f"Expected DEBUG log about missing credentials, got: {[r.getMessage() for r in caplog.records]}"


def test_log_sanitization_for_client_secret(caplog):
    """client_secret value must never appear in any log message.

    The SensitiveDataFilter (global) plus the implementation's avoidance of
    logging the secret together protect against accidental leak. This test
    is a regression guard.
    """
    secret_value = "SECRET_CLIENT_CRED_abc123xyz"
    src = TwitchSource(
        client_id="test_client_id",
        client_secret=secret_value,
        channel_logins=["anthropic"],
    )
    caplog.set_level(logging.DEBUG, logger="builderpulse.sources.twitch")

    # Trigger the missing-credentials path so we exercise the log line
    src.client_id = None
    src.fetch()

    for record in caplog.records:
        assert secret_value not in record.getMessage(), (
            f"client_secret leaked in log: {record.getMessage()!r}"
        )


def test_health_check_reflects_credentials():
    """health_check returns True only when both credentials are present."""
    assert TwitchSource(client_id="x", client_secret="y").health_check() is True
    assert TwitchSource(client_id=None, client_secret="y").health_check() is False
    assert TwitchSource(client_id="x", client_secret=None).health_check() is False
    assert TwitchSource(client_id=None, client_secret=None).health_check() is False


def test_twitchauth_get_token_caches():
    """TwitchAuth.get_token caches a fresh token and reuses it on next call."""
    call_count = [0]

    def fake_post(*_args, **_kwargs):
        call_count[0] += 1
        return httpx.Response(200, json={"access_token": "cached_token", "expires_in": 5184000})

    with respx.mock() as mock:
        mock.post("https://id.twitch.tv/oauth2/token").mock(side_effect=fake_post)
        t1 = TwitchAuth.get_token("cid", "csec")
        t2 = TwitchAuth.get_token("cid", "csec")
        t3 = TwitchAuth.get_token("cid", "csec")

    # All three calls return the same cached token, with only 1 HTTP call
    assert t1 == t2 == t3 == "cached_token"
    assert call_count[0] == 1


def test_twitchauth_invalidate_forces_refresh():
    """TwitchAuth.invalidate() forces a new token fetch on next call."""
    call_count = [0]

    def fake_post(*_args, **_kwargs):
        call_count[0] += 1
        return httpx.Response(200, json={"access_token": f"token_v{call_count[0]}", "expires_in": 5184000})

    with respx.mock() as mock:
        mock.post("https://id.twitch.tv/oauth2/token").mock(side_effect=fake_post)
        t1 = TwitchAuth.get_token("cid", "csec")
        TwitchAuth.invalidate()
        t2 = TwitchAuth.get_token("cid", "csec")

    assert t1 != t2
    assert call_count[0] == 2
