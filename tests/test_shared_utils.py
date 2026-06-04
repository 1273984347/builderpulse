"""Tests for builderpulse.core.shared_utils."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from builderpulse.core.shared_utils import (
    MIXIN_KEY_ENC_TAB,
    get_mixin_key,
    sanitize_url_for_log,
    wbi_sign,
)

# Realistic mock WBI image URLs (keys are 32 hex chars each, concatenated = 64)
_MOCK_NAV_RESPONSE = {
    "data": {
        "wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/abcdefghijklmnopqrstuvwxyz012345.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/6789ABCDEFGHIJKLMNOPQRSTUVWXYZab.png",
        }
    }
}


# -- MIXIN_KEY_ENC_TAB constant --


def test_mixin_key_enc_tab_length():
    assert len(MIXIN_KEY_ENC_TAB) == 64


def test_mixin_key_enc_tab_values_unique():
    assert len(set(MIXIN_KEY_ENC_TAB)) == 64


def test_mixin_key_enc_tab_range():
    """All indices must be valid for a 64-char raw key."""
    assert all(0 <= i < 64 for i in MIXIN_KEY_ENC_TAB)


# -- get_mixin_key --


def test_get_mixin_key_returns_32_chars():
    raw = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    key = get_mixin_key(raw)
    assert len(key) == 32
    assert isinstance(key, str)


def test_get_mixin_key_deterministic():
    raw = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert get_mixin_key(raw) == get_mixin_key(raw)


# -- wbi_sign --


def _make_mock_client() -> MagicMock:
    """Create a mock httpx.Client returning realistic WBI nav data."""
    mock_client = MagicMock()
    mock_client.get.return_value.json.return_value = _MOCK_NAV_RESPONSE
    return mock_client


def test_wbi_sign_returns_dict():
    result = wbi_sign({"test": "value"}, _make_mock_client())
    assert "w_rid" in result
    assert "wts" in result


def test_wbi_sign_deterministic():
    """Same params + same mock yields same result (frozen time)."""
    client = _make_mock_client()
    with patch("builderpulse.core.shared_utils.time") as mock_time:
        mock_time.time.return_value = 1700000000
        r1 = wbi_sign({"a": "1"}, client)
        r2 = wbi_sign({"a": "1"}, client)
    assert r1 == r2


def test_wbi_sign_sets_wts():
    result = wbi_sign({"test": "value"}, _make_mock_client())
    assert "wts" in result
    assert result["wts"].isdigit()  # wts is a numeric string after filtering


def test_wbi_sign_removes_forbidden_chars():
    result = wbi_sign({"key": "va(lue)"}, _make_mock_client())
    assert "(" not in result["key"]
    assert ")" not in result["key"]


def test_wbi_sign_sorts_params():
    client = _make_mock_client()
    with patch("builderpulse.core.shared_utils.time") as mock_time:
        mock_time.time.return_value = 1700000000
        result = wbi_sign({"z": "1", "a": "2"}, client)
    # w_rid should be the same regardless of input dict order
    with patch("builderpulse.core.shared_utils.time") as mock_time:
        mock_time.time.return_value = 1700000000
        result2 = wbi_sign({"a": "2", "z": "1"}, client)
    assert result["w_rid"] == result2["w_rid"]


# -- sanitize_url_for_log --


def test_sanitize_url_for_log_redacts_w_rid():
    url = "https://api.bilibili.com/x/web-interface/view?bvid=BV123&w_rid=abc123&wts=1700000000"
    sanitized = sanitize_url_for_log(url)
    assert "w_rid=abc123" not in sanitized
    assert "w_rid=REDACTED" in sanitized


def test_sanitize_url_for_log_redacts_wts():
    url = "https://api.bilibili.com/x/web-interface/view?bvid=BV123&wts=1700000000"
    sanitized = sanitize_url_for_log(url)
    assert "wts=1700000000" not in sanitized
    assert "wts=REDACTED" in sanitized


def test_sanitize_url_for_log_redacts_sessdata():
    url = "https://api.bilibili.com/x/player?sessdata=secret123"
    sanitized = sanitize_url_for_log(url)
    assert "secret123" not in sanitized
    assert "sessdata=REDACTED" in sanitized


def test_sanitize_url_for_log_preserves_safe_params():
    url = "https://api.bilibili.com/x/web-interface/view?bvid=BV123&cid=456"
    sanitized = sanitize_url_for_log(url)
    assert "bvid=BV123" in sanitized
    assert "cid=456" in sanitized


def test_sanitize_url_for_log_no_params():
    url = "https://api.bilibili.com/x/web-interface/nav"
    assert sanitize_url_for_log(url) == url
