"""Twitch VODs source — fetch recent VODs from configured Twitch channels.

Implements:
- OAuth Client Credentials flow (no user OAuth)
- Thread-safe in-memory token cache with 50-day TTL (10-day buffer before
  the official ~60-day expiry)
- 401 → refresh token + retry once
- channel_logins normalized to lowercase
- Get Videos uses the numeric ``id`` returned by Get Users — never
  ``login`` or ``display_name`` (the spec is explicit about this)
- Missing-credential behavior: log DEBUG + skip (no raise, no block)

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.1
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from builderpulse.core.error_codes import ErrorCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level token cache (in-memory; no file persistence)
# ---------------------------------------------------------------------------

# Spec: TTL 50 days (10-day buffer before official ~60-day expiry)
_TOKEN_TTL_SECONDS = 50 * 24 * 60 * 60

# Minimum gap between refreshes (seconds) — prevents thundering herd when
# multiple threads hit 401 simultaneously. After one thread refreshes,
# other threads within this window will reuse the freshly-fetched token
# instead of issuing their own refresh.
_REFRESH_COOLDOWN_SECONDS = 5.0

_token_cache: dict = {
    "access_token": None,
    "expires_at": 0.0,
    "last_refresh_at": 0.0,
}
_token_cache_lock = threading.Lock()


class TwitchAuth:
    """OAuth Client Credentials helper for the Twitch Helix API.

    The cache is module-level so the process-wide ``_token_cache_lock``
    is shared across all instances. This is intentional: a process only
    needs ONE valid token at a time, and centralising prevents multiple
    threads from each calling the token endpoint.
    """

    @staticmethod
    def _fetch_token(client_id: str, client_secret: str) -> str:
        """POST to the token endpoint and return the new access token."""
        resp = httpx.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        # Intentionally do NOT log token; also do NOT log client_secret
        # (the global SensitiveDataFilter additionally redacts token=... substrings)
        return token

    @classmethod
    def get_token(cls, client_id: str, client_secret: str) -> str:
        """Return a valid access token, fetching a new one if the cache is empty/expired.

        Thread-safe: only one thread can fetch a new token at a time. Other
        threads block on the lock and then read the freshly-cached token
        (prevents thundering herd on cold cache).
        """
        with _token_cache_lock:
            now = time.time()
            cached = _token_cache["access_token"]
            expires_at = _token_cache["expires_at"]
            if cached and now < expires_at:
                return cached
            # Cold or expired — fetch under lock so only one thread refreshes
            token = cls._fetch_token(client_id, client_secret)
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = now + _TOKEN_TTL_SECONDS
            return token

    @classmethod
    def refresh_token(cls, client_id: str, client_secret: str) -> str:
        """Force a fresh token fetch and update the cache (called on 401).

        Uses a cooldown window to prevent thundering herd: if another
        thread refreshed the token within ``_REFRESH_COOLDOWN_SECONDS``,
        the freshly-fetched token is reused. Atomic: invalidate + fetch
        happen under the same lock, so concurrent threads racing on 401
        responses collapse to a single token endpoint call (or, at worst,
        one call per cooldown window).
        """
        with _token_cache_lock:
            now = time.time()
            # If a refresh happened very recently, reuse the new token
            # instead of issuing our own (thundering-herd prevention).
            if (
                _token_cache["access_token"]
                and (now - _token_cache["last_refresh_at"]) < _REFRESH_COOLDOWN_SECONDS
            ):
                return _token_cache["access_token"]
            # No recent refresh — invalidate and fetch under this lock
            _token_cache["access_token"] = None
            _token_cache["expires_at"] = 0.0
            token = cls._fetch_token(client_id, client_secret)
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = now + _TOKEN_TTL_SECONDS
            _token_cache["last_refresh_at"] = now
            logger.debug("Twitch token refreshed (post-401)")
            return token

    @classmethod
    def invalidate(cls) -> None:
        """Clear the token cache (legacy helper; prefer ``refresh_token``).

        Kept for backwards compatibility / explicit invalidation. The 401
        recovery path uses ``refresh_token`` so the invalidation+refresh
        is atomic.
        """
        with _token_cache_lock:
            _token_cache["access_token"] = None
            _token_cache["expires_at"] = 0.0
        logger.debug("Twitch token cache invalidated")


# ---------------------------------------------------------------------------
# TwitchSource
# ---------------------------------------------------------------------------


class TwitchSource:
    """Fetch recent VODs from configured Twitch channels via the Helix API.

    Items are returned as plain ``dict`` (not ``FeedItem``) to keep this
    source self-contained — the orchestrator normalises shapes later.
    The dict shape matches the convention used by other v2.1.0 sources
    (see ``github_trending`` for the FeedItem variant).

    Spec: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.1
    """

    name = "twitch"
    # Pinned at v2.1.0 — this source is stable (not experimental).
    __experimental__ = False

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        channel_logins: list[str] | None = None,
        rate_limit_points_per_minute: int = 800,
        **kwargs: Any,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        # Normalize logins to lowercase for case-insensitive lookup
        self.channel_logins = [login.lower() for login in (channel_logins or [])]
        self.rate_limit_points_per_minute = rate_limit_points_per_minute
        # Simple shared httpx client (one connection pool per source instance)
        self._client = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "builderpulse/2.1.0"},
        )

    # -- public API ----------------------------------------------------------

    def fetch(self, **kwargs: Any) -> list[dict]:
        """Fetch recent VODs for all configured channels.

        Returns an empty list on any failure (no raise) so a single source
        outage does not block the rest of the pipeline.
        """
        # Missing-credential behavior: log DEBUG + skip (do NOT raise, do NOT block)
        if not self.client_id or not self.client_secret:
            logger.debug(
                "Twitch source %s skipped: client_id or client_secret missing (%s)",
                self.name,
                ErrorCode.SOURCE_MISSING_CREDENTIALS.value,
            )
            return []

        if not self.channel_logins:
            logger.debug(
                "Twitch source %s: no channel_logins configured; nothing to fetch"
            )
            return []

        try:
            user_ids = self._fetch_user_ids()
            if not user_ids:
                logger.debug(
                    "Twitch: no user IDs resolved from logins %s", self.channel_logins
                )
                return []
            return self._fetch_videos(user_ids)
        except httpx.HTTPStatusError as exc:
            # 401 → refresh token (atomic invalidate+fetch under lock) and retry once
            if exc.response.status_code == 401:
                logger.debug("Twitch 401 received; refreshing token and retrying once")
                TwitchAuth.refresh_token(self.client_id, self.client_secret)
                try:
                    user_ids = self._fetch_user_ids()
                    if user_ids:
                        return self._fetch_videos(user_ids)
                except httpx.HTTPStatusError as exc2:
                    logger.error("Twitch still failing after token refresh: %s", exc2)
                    return []
                return []
            logger.error("Twitch HTTP error: %s", exc)
            return []
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Twitch fetch failed: %s", exc)
            return []

    def health_check(self) -> bool:
        """Cheap health probe — returns True only when both credentials are set.

        We do NOT call out to Twitch here (cost). The actual fetch will
        surface real errors via the per-step try/except paths.
        """
        return self.client_id is not None and self.client_secret is not None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TwitchSource":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- internals -----------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build auth headers for a Helix API call."""
        token = TwitchAuth.get_token(self.client_id, self.client_secret)
        return {
            "Authorization": f"Bearer {token}",
            "Client-Id": self.client_id,
        }

    def _fetch_user_ids(self) -> list[str]:
        """Convert ``channel_logins`` → numeric user IDs via Get Users.

        Uses the batch form ``?login=a&login=b`` to minimise rate-limit
        point cost (one call returns up to 100 logins).
        """
        params: list[tuple[str, str]] = [
            ("login", login) for login in self.channel_logins
        ]
        resp = self._client.get(
            "https://api.twitch.tv/helix/users",
            params=params,
            headers=self._get_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        # CRITICAL: use id (numeric), NEVER login or display_name.
        # The spec is explicit: "The response id (numeric string) is used
        # for Get Videos — never display_name or login."
        return [user["id"] for user in data.get("data", [])]

    def _fetch_videos(self, user_ids: list[str]) -> list[dict]:
        """Get recent VODs for the given numeric user IDs."""
        params: list[tuple[str, str]] = [("user_id", uid) for uid in user_ids]
        resp = self._client.get(
            "https://api.twitch.tv/helix/videos",
            params=params,
            headers=self._get_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        items: list[dict] = []
        for v in data.get("data", []):
            items.append(
                {
                    "url": v.get("url", ""),
                    "title": v.get("title", ""),
                    "published_at": v.get("published_at"),
                    "source": "twitch",
                    "sub_source": "videos",
                    "user_id": v.get("user_id"),
                    "user_login": v.get("user_login"),
                }
            )
        return items
