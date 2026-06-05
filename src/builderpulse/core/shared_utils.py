"""Shared utilities for Bilibili API interactions.

Extracted from engines/downloaders/bilibili.py and sources/bilibili.py
to eliminate code duplication.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

# WBI mixin key encoding table (from Bilibili web frontend)
MIXIN_KEY_ENC_TAB: list[int] = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
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


def wbi_sign(params: dict, client: httpx.Client) -> dict:
    """Sign parameters using Bilibili WBI algorithm.

    Fetches the current WBI keys from the nav API, computes the mixin key,
    and signs the given parameters. Returns a new dict with ``wts`` and
    ``w_rid`` added.

    Args:
        params: Request parameters to sign.
        client: An httpx.Client instance used to call the Bilibili nav API.

    Returns:
        A copy of *params* with ``wts`` (timestamp) and ``w_rid`` (signature)
        added.
    """
    nav = client.get("https://api.bilibili.com/x/web-interface/nav").json()
    wbi_img = nav.get("data", {}).get("wbi_img", {})
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")

    img_key = img_url.split("/")[-1].split(".")[0] if img_url else ""
    sub_key = sub_url.split("/")[-1].split(".")[0] if sub_url else ""

    mixin_key = get_mixin_key(img_key + sub_key)

    signed = dict(params)
    signed["wts"] = int(time.time())
    # Sort and filter forbidden characters
    signed = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted(signed.items())
    }
    query = urllib.parse.urlencode(signed)
    # MD5 is required by Bilibili's WBI signing protocol. Not a security
    # weakness here — the signature is per-request, never reused, and the
    # signed payload contains no secrets. See:
    # https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/sign/other.html
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()  # codeql[py/weak-sensitive-data-hashing]
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
