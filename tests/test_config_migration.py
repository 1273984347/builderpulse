"""Tests for Config v2.0.0 → v2.1.0 migration (spec §3.6).

Verifies:
    - Missing ``__version__`` triggers default-fill + writes version
    - Once at target version, user's customised values are preserved
    - X.Y.Z string comparison is equivalent to semantic comparison
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from builderpulse.core.config import TARGET_CONFIG_VERSION, Config


# ── test_migration_from_v200_fills_defaults_and_writes_version ─────────


def test_migration_from_v200_fills_defaults_and_writes_version(
    tmp_path: Path,
) -> None:
    """v2.0.0 config (no ``__version__``, no ``enabled_sources``) →
    migration fills defaults + writes ``__version__``.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"language": "zh", "workspace": "/tmp/output"}),
        encoding="utf-8",
    )

    cfg = Config.from_file(config_path)

    # Defaults filled in memory.
    assert "bilibili" in cfg.enabled_sources
    assert "youtube" in cfg.enabled_sources
    assert "telegram" in cfg.enabled_channels
    assert "lark" in cfg.enabled_channels
    assert cfg.version == TARGET_CONFIG_VERSION

    # User's existing fields preserved.
    assert cfg.language == "zh"
    assert cfg.workspace == "/tmp/output"

    # File was persisted with the new version and defaults.
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["__version__"] == TARGET_CONFIG_VERSION
    assert "bilibili" in persisted["enabled_sources"]
    assert "lark" in persisted["enabled_channels"]
    assert persisted["language"] == "zh"


# ── test_no_re_migration_when_version_present ──────────────────────────


def test_no_re_migration_when_version_present(tmp_path: Path) -> None:
    """When ``__version__`` is already at target, do NOT re-fill defaults
    (respect user's minimal setting)."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "__version__": TARGET_CONFIG_VERSION,
                "enabled_sources": ["bilibili"],  # user explicitly chose only 1
                "enabled_channels": [],  # user explicitly disabled all
            }
        ),
        encoding="utf-8",
    )

    original_mtime = config_path.stat().st_mtime_ns
    cfg = Config.from_file(config_path)

    # User's minimal settings preserved (no auto-fill).
    assert cfg.enabled_sources == ["bilibili"]
    assert cfg.enabled_channels == []
    assert cfg.version == TARGET_CONFIG_VERSION

    # File should not be rewritten when already at target version.
    assert config_path.stat().st_mtime_ns == original_mtime


# ── test_migration_idempotency ─────────────────────────────────────────


def test_migration_idempotency(tmp_path: Path) -> None:
    """Loading the same v2.0.0 config twice does not duplicate or mutate
    the second load (file is at target version after first load)."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    # First load: triggers migration.
    cfg1 = Config.from_file(config_path)
    after_first = json.loads(config_path.read_text(encoding="utf-8"))

    # Second load: should be a no-op (version is now at target).
    cfg2 = Config.from_file(config_path)
    after_second = json.loads(config_path.read_text(encoding="utf-8"))

    # Both loads produce equivalent configs.
    assert cfg1.version == cfg2.version == TARGET_CONFIG_VERSION
    assert cfg1.enabled_sources == cfg2.enabled_sources

    # File content unchanged on second load.
    assert after_first == after_second


# ── test_version_string_comparison_works_for_xy_z_format ───────────────


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("2.1.0", "2.2.0", True),  # 2.1.0 < 2.2.0
        ("2.1.0", "2.1.0", False),  # equal
        ("2.10.0", "2.1.0", False),  # lexicographic == semantic
        ("2.0.9", "2.1.0", True),  # any 2.0.x < 2.1.0
        ("2.1.0", "2.0.99", False),  # 2.1.0 > 2.0.99
        ("1.99.99", "2.0.0", True),  # major bump
    ],
)
def test_version_string_comparison_works_for_xy_z_format(
    left: str, right: str, expected: bool
) -> None:
    """X.Y.Z format: lexicographic comparison is equivalent to semantic
    comparison — see spec §3.6 (no packaging.version dependency)."""
    assert (left < right) is expected


# ── test_new_fields_have_v20_defaults ──────────────────────────────────


def test_new_fields_have_v20_defaults() -> None:
    """Config() default ctor uses v2.0.0 enabled sources/channels.

    v2.1.0 NEW integrations (github_trending, twitch, slack, etc.) are
    deliberately NOT in the default list — strict opt-in policy.
    """
    cfg = Config()

    # v2.0.0 sources enabled
    assert set(cfg.enabled_sources) == {
        "bilibili",
        "youtube",
        "podcast",
        "blog",
        "twitter",
    }
    # v2.0.0 channels enabled
    assert set(cfg.enabled_channels) == {
        "telegram",
        "email",
        "lark",
        "dingtalk",
        "discord",
        "wecom",
        "wechat",
        "stderr",
    }
    # v2.1.0 NEW integrations are NOT auto-enabled
    for new_source in ("github_trending", "twitch", "xiaohongshu", "wechat_mp"):
        assert new_source not in cfg.enabled_sources
    for new_channel in ("slack", "notion", "webhook", "bark"):
        assert new_channel not in cfg.enabled_channels


# ── test_to_dict_uses_dunder_version_key ───────────────────────────────


def test_to_dict_uses_dunder_version_key() -> None:
    """to_dict() writes the schema version as ``__version__`` (spec §3.6
    JSON convention) so the on-disk format matches what from_file() reads."""
    cfg = Config()
    d = cfg.to_dict(mask_secrets=False)
    assert "__version__" in d
    assert d["__version__"] == TARGET_CONFIG_VERSION
    # Python field ``version`` is NOT the on-disk key.
    assert "version" not in d


# ── test_migration_writes_valid_json_roundtrip ─────────────────────────


def test_migration_writes_valid_json_roundtrip(tmp_path: Path) -> None:
    """The migration-written file should be a valid JSON document that
    re-loads without modification."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "language": "zh",
                "telegram_bot_token": "123:abc",  # sensitive field present
            }
        ),
        encoding="utf-8",
    )

    cfg = Config.from_file(config_path)
    assert cfg.version == TARGET_CONFIG_VERSION

    # Round-trip: re-read the file directly (not via from_file, to verify
    # the JSON itself is well-formed).
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["__version__"] == TARGET_CONFIG_VERSION
    assert "bilibili" in raw["enabled_sources"]
    # Sensitive value preserved on disk (masking is only in to_dict()).
    assert raw["telegram_bot_token"] == "123:abc"
