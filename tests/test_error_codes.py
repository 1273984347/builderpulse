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


# ── v2.1.0 additions: SOURCE_MISSING_CREDENTIALS, SOURCE_AUTO_DISABLED, CHANNEL_DISABLED ──


def test_new_error_codes_exist():
    """v2.1.0 error codes exist with dotted lowercase values per spec §3.4."""
    assert ErrorCode.SOURCE_MISSING_CREDENTIALS.value == "source.missing_credentials"
    assert ErrorCode.SOURCE_AUTO_DISABLED.value == "source.auto_disabled"
    assert ErrorCode.CHANNEL_DISABLED.value == "channel.disabled"


def test_error_codes_are_json_serializable():
    """New error code values are JSON-serializable (string enum value usable in JSON payloads)."""
    import json
    data = {"code": ErrorCode.SOURCE_MISSING_CREDENTIALS.value}
    assert json.dumps(data)  # should not raise


def test_error_codes_iterate_includes_new():
    """ErrorCode iteration includes the new v2.1.0 codes."""
    all_codes = [c.value for c in ErrorCode]
    assert "source.missing_credentials" in all_codes
    assert "source.auto_disabled" in all_codes
    assert "channel.disabled" in all_codes
