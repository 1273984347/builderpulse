"""Shared utilities for Bilibili API interactions.

Extracted from engines/downloaders/bilibili.py and sources/bilibili.py
to eliminate code duplication.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

# WBI key cache: 30 min TTL (per v2.0.1 design spec).
# The mixin key is derived from Bilibili's nav response and rotates server-side
# every few months; 30 min is far shorter than the rotation interval, so cache
# hit rate is high in steady state and stale-key risk is bounded.
#
# TODO(v2.2+): Background proactive refresh when TTL < 10% remaining.
# Tracked: https://github.com/1273984347/builderpulse/issues/XXX
# (deferred from v2.0.1 patch scope per spec §2 — needs timer/thread
# management not appropriate for a tiny patch.)
WBI_CACHE_TTL_SECONDS: int = 30 * 60

# Module-level cache state. Dict (not a custom class) keeps the public surface
# minimal and makes the cache trivially inspectable from tests.
_wbi_cache: dict = {"key": None, "fetched_at": 0.0}
_wbi_cache_lock = threading.Lock()

_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

# WBI mixin key encoding table (from Bilibili web frontend)
MIXIN_KEY_ENC_TAB: list[int] = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

_SENSITIVE_PARAMS = frozenset({"w_rid", "wts", "sessdata", "SESSDATA"})


def get_mixin_key(raw: str) -> str:
    """Compute 32-char mixin key from a raw key string using the encoding table.

    Args:
        raw: Concatenated img_key + sub_key (must be >= 64 chars).

    Returns:
        32-character mixin key string.
    """
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _fetch_wbi_key_from_bilibili(client: httpx.Client) -> str:
    """Fetch a fresh WBI mixin key from the Bilibili nav API.

    Returns the 32-character mixin key derived from the nav response's
    img_url + sub_url. Used by :func:`get_wbi_key` on cache miss.

    Args:
        client: httpx.Client used to call the Bilibili nav endpoint.

    Returns:
        The 32-char mixin key.

    Raises:
        RuntimeError: If the nav response is missing ``wbi_img``,
            ``img_url``, or ``sub_url`` (or returns empty strings for
            them). The caller (:func:`get_wbi_key`) does not store the
            cache value on exception, so the next call will retry —
            preferable to caching an empty/garbage key for 30 min and
            silently producing invalid signatures (-6 errors).
    """
    nav = client.get(_NAV_URL).json()
    wbi_img = nav.get("data", {}).get("wbi_img", {})
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")

    if not img_url or not sub_url:
        raise RuntimeError(
            "Bilibili nav response missing wbi_img/img_url/sub_url"
        )

    img_key = img_url.split("/")[-1].split(".")[0]
    sub_key = sub_url.split("/")[-1].split(".")[0]

    return get_mixin_key(img_key + sub_key)


def get_wbi_key(client: httpx.Client) -> str:
    """Return the cached WBI mixin key, refreshing on miss or TTL expiry.

    Thread-safe: the lock is held across the freshness check and the fetch,
    so concurrent callers serialize on a single in-flight fetch instead of
    stampeding the Bilibili nav API.

    The cached value is never logged in full — log lines reference the cache
    state (hit/miss/invalidated) but not the key bytes themselves.

    Args:
        client: httpx.Client passed through to the fetcher on cache miss.

    Returns:
        The 32-character WBI mixin key.
    """
    with _wbi_cache_lock:
        now = time.time()
        if (
            _wbi_cache["key"] is not None
            and (now - _wbi_cache["fetched_at"]) < WBI_CACHE_TTL_SECONDS
        ):
            return _wbi_cache["key"]
        key = _fetch_wbi_key_from_bilibili(client)
        _wbi_cache["key"] = key
        _wbi_cache["fetched_at"] = now
        return key


def invalidate_wbi_cache() -> None:
    """Clear the WBI cache (e.g., after a -6 signature error from Bilibili).

    The next call to :func:`get_wbi_key` will re-fetch from the nav API.
    Safe to call from any thread.
    """
    with _wbi_cache_lock:
        _wbi_cache["key"] = None
        _wbi_cache["fetched_at"] = 0.0
    logger.debug("WBI cache invalidated")


def wbi_sign(params: dict, client: httpx.Client) -> dict:
    """Sign parameters using Bilibili WBI algorithm.

    Fetches (or reuses) the cached WBI mixin key, then signs the given
    parameters. Returns a new dict with ``wts`` and ``w_rid`` added.

    Args:
        params: Request parameters to sign.
        client: An httpx.Client instance used to call the Bilibili nav API
            when the cache is cold.

    Returns:
        A copy of *params* with ``wts`` (timestamp) and ``w_rid`` (signature)
        added.
    """
    mixin_key = get_wbi_key(client)

    signed = dict(params)
    signed["wts"] = int(time.time())
    # Sort and filter forbidden characters
    signed = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted(signed.items())
    }
    query = urllib.parse.urlencode(signed)
    # MD5 is required by Bilibili's WBI signing protocol. Per-request, never
    # reused, no secrets in payload. See:
    # https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/sign/other.html
    # codeql[py/weak-sensitive-data-hashing]
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed


def sanitize_url_for_log(url: str) -> str:
    """Redact sensitive parameters from a URL for safe logging.

    Replaces the values of ``w_rid``, ``wts``, ``sessdata``, and ``SESSDATA``
    query parameters with ``REDACTED``.

    Args:
        url: The URL to sanitize.

    Returns:
        The URL with sensitive parameter values replaced.
    """
    if not any(p in url for p in _SENSITIVE_PARAMS):
        return url
    result = url
    for param in _SENSITIVE_PARAMS:
        result = re.sub(
            rf"({param}=)[^&]*",
            r"\g<1>REDACTED",
            result,
        )
    return result
