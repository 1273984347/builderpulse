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
