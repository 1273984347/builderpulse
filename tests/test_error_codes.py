"""Tests for builderpulse.core.error_codes."""

from __future__ import annotations

from builderpulse.core.error_codes import (
    ErrorCode,
    register_plugin_code,
    get_error_info,
)


def test_error_code_values():
    """ErrorCode members match their string values."""
    assert ErrorCode.DOWNLOAD_FAILED == "DOWNLOAD_FAILED"
    assert ErrorCode.DOWNLOAD_TIMEOUT == "DOWNLOAD_TIMEOUT"
    assert ErrorCode.DOWNLOAD_FORBIDDEN == "DOWNLOAD_FORBIDDEN"
    assert ErrorCode.TRANSCRIBE_FAILED == "TRANSCRIBE_FAILED"
    assert ErrorCode.TRANSCRIBE_NO_AUDIO == "TRANSCRIBE_NO_AUDIO"
    assert ErrorCode.TRANSCRIBE_ENGINE_UNAVAILABLE == "TRANSCRIBE_ENGINE_UNAVAILABLE"
    assert ErrorCode.SUMMARIZE_FAILED == "SUMMARIZE_FAILED"
    assert ErrorCode.SUMMARIZE_QUOTA_EXCEEDED == "SUMMARIZE_QUOTA_EXCEEDED"
    assert ErrorCode.TRANSLATE_FAILED == "TRANSLATE_FAILED"
    assert ErrorCode.DELIVER_FAILED == "DELIVER_FAILED"
    assert ErrorCode.DELIVER_RATE_LIMITED == "DELIVER_RATE_LIMITED"
    assert ErrorCode.BATCH_ITEM_FAILED == "BATCH_ITEM_FAILED"
    assert ErrorCode.BATCH_DISK_FULL == "BATCH_DISK_FULL"
    assert ErrorCode.CONFIG_NOT_FOUND == "CONFIG_NOT_FOUND"
    assert ErrorCode.CONFIG_INVALID == "CONFIG_INVALID"


def test_register_plugin_code():
    """register_plugin_code returns PLUGIN_{plugin}_{code} and stores it."""
    code = register_plugin_code("bilibili", "SIGN_FAILED", "WBI signing failed")
    assert code == "PLUGIN_BILIBILI_SIGN_FAILED"


def test_get_error_info_core():
    """get_error_info returns type=core for built-in codes."""
    info = get_error_info("DOWNLOAD_FAILED")
    assert info["type"] == "core"
    assert "DOWNLOAD_FAILED" in info["code"]


def test_get_error_info_plugin():
    """get_error_info returns type=plugin for plugin-registered codes."""
    register_plugin_code("test", "ERR", "test error")
    info = get_error_info("PLUGIN_TEST_ERR")
    assert info["type"] == "plugin"
    assert info["plugin"] == "test"


def test_get_error_info_unknown():
    """get_error_info handles unknown codes gracefully."""
    info = get_error_info("UNKNOWN_CODE")
    assert info["type"] == "unknown"
