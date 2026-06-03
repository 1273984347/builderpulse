"""Tests for infra.secrets module."""
from __future__ import annotations

import pytest

from builderpulse.infra.secrets import get_secret, is_sensitive, mask_value


class TestGetSecret:
    """Tests for get_secret()."""

    def test_get_secret_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var BUILDERPULSE_<KEY> is returned when set."""
        monkeypatch.setenv("BUILDERPULSE_API_KEY", "env-secret-123")
        # Ensure keyring is not importable so it falls through
        monkeypatch.setitem(__import__("sys").modules, "keyring", None)
        result = get_secret("api_key")
        assert result == "env-secret-123"

    def test_get_secret_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when no source has the key."""
        # Ensure env var is not set
        monkeypatch.delenv("BUILDERPULSE_NONEXISTENT", raising=False)
        # Block keyring import
        monkeypatch.setitem(__import__("sys").modules, "keyring", None)
        result = get_secret("nonexistent")
        assert result is None


class TestMaskValue:
    """Tests for mask_value()."""

    def test_mask_value(self) -> None:
        """Normal string: first 2 + last 2 visible, middle masked."""
        assert mask_value("abcdef") == "ab**ef"

    def test_mask_value_short(self) -> None:
        """String <= 4 chars is fully masked."""
        assert mask_value("abc") == "****"

    def test_mask_value_empty(self) -> None:
        """Empty/None returns empty string."""
        assert mask_value("") == ""
        assert mask_value(None) == ""


class TestIsSensitive:
    """Tests for is_sensitive()."""

    def test_is_sensitive_true(self) -> None:
        """Known sensitive key returns True."""
        assert is_sensitive("api_key") is True

    def test_is_sensitive_false(self) -> None:
        """Non-sensitive key returns False."""
        assert is_sensitive("language") is False
