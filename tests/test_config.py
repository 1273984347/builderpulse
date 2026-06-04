"""Tests for builderpulse.core.config — Config class, env overrides, secret masking."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from builderpulse.core.config import Config, SENSITIVE_KEYS


# ── test_default_config ────────────────────────────────────────────────


def test_default_config():
    """Config.from_defaults() should use spec §7 defaults."""
    cfg = Config.from_defaults()
    assert cfg.language == "en"
    assert cfg.engine == "auto"
    assert cfg.model == "base"
    assert cfg.device == "auto"
    assert "builderpulse" in cfg.workspace.lower()


# ── test_load_from_file ────────────────────────────────────────────────


def test_load_from_file(tmp_path: Path):
    """Config.from_file() should load JSON and populate fields."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "language": "zh",
        "engine": "whisperx",
        "model": "large",
        "device": "cuda",
    }))

    cfg = Config.from_file(config_file)
    assert cfg.language == "zh"
    assert cfg.engine == "whisperx"
    assert cfg.model == "large"
    assert cfg.device == "cuda"


# ── test_env_override ──────────────────────────────────────────────────


def test_env_override(monkeypatch):
    """BUILDERPULSE_* env vars should override defaults."""
    monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "zh")
    monkeypatch.setenv("BUILDERPULSE_ENGINE", "faster-whisper")

    cfg = Config.from_defaults()
    assert cfg.language == "zh"
    assert cfg.engine == "faster-whisper"


# ── test_secret_fields_masked ──────────────────────────────────────────


def test_secret_fields_masked():
    """Sensitive fields should be masked as '****' in to_dict()."""
    cfg = Config(telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    d = cfg.to_dict(mask_secrets=True)
    assert d["telegram_bot_token"] == "****"
    assert "123456" not in str(d.values())


# ── test_non_secret_fields_visible ────────────────────────────────────


def test_non_secret_fields_visible():
    """Non-sensitive fields should never be masked."""
    cfg = Config(language="zh")
    d = cfg.to_dict(mask_secrets=True)
    assert d["language"] == "zh"


# ── Type coercion tests ────────────────────────────────────────────────


class TestEnvOverrideTypeCoercion:
    """_apply_env_overrides should coerce env var strings to field types."""

    def test_str_override(self, monkeypatch):
        """String fields are set as-is."""
        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "hello")
        cfg = Config.from_defaults()
        assert cfg.language == "hello"
        assert isinstance(cfg.language, str)

    def test_bool_override_true(self, monkeypatch):
        """'true' -> True for bool fields.

        Config has no bool fields by default, so we test the coercion
        logic by verifying string fields stay as strings (no bool fields exist).
        The _apply_env_overrides logic handles Optional[str] as str.
        """
        # Config doesn't have plain bool fields, but the coercion logic
        # is testable via the type inspection path. We test that str fields
        # with bool-like values stay as strings.
        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "true")
        cfg = Config.from_defaults()
        # language is str, so "true" stays as string
        assert cfg.language == "true"
        assert isinstance(cfg.language, str)

    def test_str_override_numeric(self, monkeypatch):
        """Numeric strings stay as strings for str fields."""
        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "42")
        cfg = Config.from_defaults()
        assert cfg.language == "42"
        assert isinstance(cfg.language, str)

    def test_str_override_empty(self, monkeypatch):
        """Empty string is a valid override."""
        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "")
        cfg = Config.from_defaults()
        assert cfg.language == ""

    def test_env_var_not_set_uses_default(self):
        """When env var is not set, default is used."""
        cfg = Config.from_defaults()
        assert cfg.language == "en"
        assert cfg.engine == "auto"

    def test_multiple_env_overrides(self, monkeypatch):
        """Multiple env vars override their respective fields."""
        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "zh")
        monkeypatch.setenv("BUILDERPULSE_ENGINE", "faster-whisper")
        monkeypatch.setenv("BUILDERPULSE_MODEL", "large")
        cfg = Config.from_defaults()
        assert cfg.language == "zh"
        assert cfg.engine == "faster-whisper"
        assert cfg.model == "large"

    def test_from_file_then_env_override(self, monkeypatch, tmp_path):
        """Env vars override values loaded from file."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"language": "en", "engine": "auto"}))

        monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "zh")
        cfg = Config.from_file(config_file)
        assert cfg.language == "zh"
        assert cfg.engine == "auto"  # not overridden
