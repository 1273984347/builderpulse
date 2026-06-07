"""Tests for BatchManager.run() — sources_override / channels_override (v2.1.0 spec §3.9).

Spec §3.9: ``BatchManager.run`` accepts optional ``sources_override`` and
``channels_override`` kwargs that bypass the config's ``enabled_sources`` /
``enabled_channels``.  Safety checks are performed BEFORE fetching:

  * Experimental sources (xiaohongshu, wechat_mp) require ``proxy_url``
  * Twitch requires ``client_id`` + ``client_secret``
  * Channels require their credential fields (slack needs ``webhook_url``,
    notion needs ``token``, bark needs ``device_key``, webhook needs ``url``)

On a missing-credential override the manager logs ERROR and skips the
source/channel — it never raises.  The override that *passes* the check is
logged at INFO.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from builderpulse.batch.manager import BatchManager


def _empty_registry() -> dict:
    """Return an empty plugin dict for ``PluginRegistry.list``."""
    return {}


@pytest.fixture
def empty_registry():
    """Patch ``PluginRegistry.list`` to return ``{}`` so ``run()`` short-circuits."""
    with patch("builderpulse.plugins.registry.PluginRegistry.list", return_value={}):
        yield


# ── Happy-path: override accepted ──────────────────────────────────────


class TestRunWithOverrides:
    """Override kwargs are accepted and trigger no error when credentials are valid."""

    def test_run_with_sources_override_ignores_enabled_sources_config(
        self, tmp_path, empty_registry, caplog
    ):
        """sources_override bypasses the config's enabled_sources list.

        With an empty registry there's nothing to actually fetch — the
        contract is that ``run()`` accepts the kwarg and does not raise
        when credentials are configured (or no credentials are required
        for a non-experimental, non-credentialed source).
        """
        from builderpulse.core.config import Config

        mgr = BatchManager(db_path=tmp_path / "cache.db")

        # github_trending is not experimental and has no required creds,
        # so the override should be accepted without error.
        caplog.set_level(logging.INFO, logger="builderpulse.batch")
        # CI has no ~/.builderpulse/config.json — mock ConfigManager.get()
        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=Config(),
        ):
            with caplog.at_level(logging.INFO):
                mgr.run(sources_override=["github_trending"])

        mgr.shutdown()
        # No ERROR logs expected.
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors == [], (
            f"Expected no ERROR logs, got: {[r.getMessage() for r in errors]}"
        )

    def test_run_with_channels_override_accepted_when_credentials_present(
        self, tmp_path, empty_registry
    ):
        """channels_override is accepted when all required creds are provided."""
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.channels_config = {
            "slack": {"webhook_url": "https://hooks.slack.test/x"}
        }
        mock_config.sources_config = {}
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            # Should not raise
            mgr.run(channels_override=["slack"])

        mgr.shutdown()


# ── Safety: experimental sources require proxy_url ─────────────────────


class TestExperimentalOverrideRequiresProxy:
    """xiaohongshu / wechat_mp overrides require proxy_url in config."""

    def test_xiaohongshu_override_without_proxy_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {"xiaohongshu": {}}  # no proxy_url
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["xiaohongshu"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "xiaohongshu" in m.lower() and "proxy" in m.lower() for m in error_messages
        ), f"Expected xiaohongshu + proxy error, got: {error_messages}"

        mgr.shutdown()

    def test_wechat_mp_override_without_proxy_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {"wechat_mp": {}}  # no proxy_url
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["wechat_mp"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "wechat_mp" in m.lower() and "proxy" in m.lower() for m in error_messages
        ), f"Expected wechat_mp + proxy error, got: {error_messages}"

        mgr.shutdown()

    def test_xiaohongshu_override_with_proxy_is_accepted(
        self, tmp_path, empty_registry, caplog
    ):
        """When proxy_url is present, xiaohongshu override is accepted (no ERROR)."""
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {
            "xiaohongshu": {"proxy_url": "http://proxy.local:8080"}
        }
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["xiaohongshu"])

        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors == [], (
            f"Expected no ERROR logs, got: {[r.getMessage() for r in errors]}"
        )
        mgr.shutdown()


# ── Safety: Twitch requires client_id + client_secret ─────────────────


class TestTwitchOverrideRequiresCredentials:
    """Twitch override requires client_id and client_secret."""

    def test_twitch_override_without_client_id_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {"twitch": {"client_secret": "x"}}  # no client_id
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["twitch"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "twitch" in m.lower() and "client_id" in m.lower() for m in error_messages
        ), f"Expected twitch + client_id error, got: {error_messages}"

        mgr.shutdown()

    def test_twitch_override_without_client_secret_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {"twitch": {"client_id": "x"}}  # no secret
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["twitch"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any("twitch" in m.lower() for m in error_messages), (
            f"Expected twitch error, got: {error_messages}"
        )
        mgr.shutdown()

    def test_twitch_override_with_full_credentials_is_accepted(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = {
            "twitch": {"client_id": "abc", "client_secret": "def"}
        }
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []
        mock_config.channels_config = {}

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(sources_override=["twitch"])

        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors == [], (
            f"Expected no ERROR logs, got: {[r.getMessage() for r in errors]}"
        )
        mgr.shutdown()


# ── Safety: channels require their credential fields ─────────────────


class TestChannelsOverrideRequiresCredentials:
    """Channel override validates required credential fields per channel."""

    def test_slack_override_without_webhook_url_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.channels_config = {"slack": {}}  # no webhook_url
        mock_config.sources_config = {}
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(channels_override=["slack"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "slack" in m.lower() and "webhook_url" in m.lower() for m in error_messages
        ), f"Expected slack + webhook_url error, got: {error_messages}"

        mgr.shutdown()

    def test_notion_override_without_token_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.channels_config = {"notion": {}}  # no token
        mock_config.sources_config = {}
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(channels_override=["notion"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "notion" in m.lower() and "token" in m.lower() for m in error_messages
        ), f"Expected notion + token error, got: {error_messages}"

        mgr.shutdown()

    def test_bark_override_without_device_key_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.channels_config = {"bark": {}}  # no device_key
        mock_config.sources_config = {}
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(channels_override=["bark"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "bark" in m.lower() and "device_key" in m.lower() for m in error_messages
        ), f"Expected bark + device_key error, got: {error_messages}"

        mgr.shutdown()

    def test_webhook_override_without_url_logs_error(
        self, tmp_path, empty_registry, caplog
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.channels_config = {"webhook": {}}  # no url
        mock_config.sources_config = {}
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                mgr.run(channels_override=["webhook"])

        error_messages = [
            r.getMessage() for r in caplog.records if r.levelname == "ERROR"
        ]
        assert any(
            "webhook" in m.lower() and "url" in m.lower() for m in error_messages
        ), f"Expected webhook + url error, got: {error_messages}"

        mgr.shutdown()


# ── Contract: never raises on missing creds ────────────────────────────


class TestRunNeverRaises:
    """run() must never raise on safety-check failure — log + skip only."""

    @pytest.mark.parametrize(
        "override, sources_config, channels_config",
        [
            ({"sources_override": ["xiaohongshu"]}, {"xiaohongshu": {}}, {}),
            ({"sources_override": ["wechat_mp"]}, {"wechat_mp": {}}, {}),
            ({"sources_override": ["twitch"]}, {"twitch": {}}, {}),
            ({"channels_override": ["slack"]}, {}, {"slack": {}}),
            ({"channels_override": ["notion"]}, {}, {"notion": {}}),
            ({"channels_override": ["bark"]}, {}, {"bark": {}}),
            ({"channels_override": ["webhook"]}, {}, {"webhook": {}}),
        ],
    )
    def test_no_raise_on_missing_credentials(
        self,
        tmp_path,
        empty_registry,
        caplog,
        override,
        sources_config,
        channels_config,
    ):
        mgr = BatchManager(db_path=tmp_path / "cache.db")
        mock_config = MagicMock()
        mock_config.sources_config = sources_config
        mock_config.channels_config = channels_config
        mock_config.enabled_sources = []
        mock_config.enabled_channels = []

        with patch(
            "builderpulse.core.config_manager.ConfigManager.get",
            return_value=mock_config,
        ):
            with caplog.at_level(logging.ERROR, logger="builderpulse.batch"):
                # Must not raise
                mgr.run(**override)

        mgr.shutdown()
