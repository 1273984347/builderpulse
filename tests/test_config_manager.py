"""Tests for ConfigManager — thread-safe singleton with hot-reload."""

import threading

import pytest

from builderpulse.core.config_manager import ConfigManager


class TestConfigManager:
    """Unit tests for ConfigManager class-level singleton."""

    def setup_method(self):
        """Reset singleton state between tests."""
        ConfigManager._config = None
        ConfigManager._subscribers.clear()
        ConfigManager._instance_path = None
        ConfigManager._reloading = False
        ConfigManager._failed_callbacks.clear()

    def test_get_returns_config(self, tmp_path):
        """get() should return a Config loaded from the specified path."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text('{"language": "zh"}')
        ConfigManager.set_config_path(cfg_path)
        cfg = ConfigManager.get()
        assert cfg.language == "zh"

    def test_get_caches_config(self, tmp_path):
        """get() should return cached config on subsequent calls."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text('{"language": "zh"}')
        ConfigManager.set_config_path(cfg_path)
        cfg1 = ConfigManager.get()
        cfg2 = ConfigManager.get()
        assert cfg1 is cfg2

    def test_reload_notifies_subscribers(self, tmp_path):
        """reload() should notify all subscribers with the new config."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text('{"language": "zh"}')
        ConfigManager.set_config_path(cfg_path)
        received = []
        ConfigManager.subscribe(lambda c: received.append(c.language))
        cfg_path.write_text('{"language": "en"}')
        ConfigManager.reload()
        assert received == ["en"]

    def test_reload_reentrancy_guard(self, tmp_path):
        """reload() should return cached config if already reloading."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text("{}")
        ConfigManager.set_config_path(cfg_path)
        # Simulate reentrant call
        ConfigManager._reloading = True
        result = ConfigManager.reload()
        assert result is not None

    def test_failed_callbacks_tracked(self, tmp_path):
        """Failed subscriber callbacks should be tracked."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text("{}")
        ConfigManager.set_config_path(cfg_path)

        def bad_callback(c):
            raise RuntimeError("boom")

        ConfigManager.subscribe(bad_callback)
        ConfigManager.reload()
        assert len(ConfigManager.get_failed_callbacks()) == 1

    def test_set_config_path_thread_safe(self, tmp_path):
        """set_config_path() + get() should be safe across threads."""
        p1 = tmp_path / "c1.json"
        p1.write_text('{"language": "zh"}')
        p2 = tmp_path / "c2.json"
        p2.write_text('{"language": "en"}')
        results = []

        def switch_and_get(path):
            ConfigManager.set_config_path(path)
            results.append(ConfigManager.get().language)

        t1 = threading.Thread(target=switch_and_get, args=(p1,))
        t2 = threading.Thread(target=switch_and_get, args=(p2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(results) == 2

    def test_subscribe_adds_callback(self, tmp_path):
        """subscribe() should add callback to the subscriber list."""
        calls = []
        ConfigManager.subscribe(lambda c: calls.append(1))
        assert len(ConfigManager._subscribers) == 1

    def test_reload_clears_failed_callbacks(self, tmp_path):
        """reload() should clear old failed callbacks before notifying."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text("{}")
        ConfigManager.set_config_path(cfg_path)

        def bad_callback(c):
            raise RuntimeError("boom")

        ConfigManager.subscribe(bad_callback)
        ConfigManager.reload()
        assert len(ConfigManager.get_failed_callbacks()) == 1

        # Second reload should clear and re-track
        ConfigManager.reload()
        assert len(ConfigManager.get_failed_callbacks()) == 1

    def test_set_config_path_clears_cache(self, tmp_path):
        """set_config_path() should invalidate cached config."""
        p1 = tmp_path / "c1.json"
        p1.write_text('{"language": "zh"}')
        p2 = tmp_path / "c2.json"
        p2.write_text('{"language": "en"}')

        ConfigManager.set_config_path(p1)
        cfg1 = ConfigManager.get()
        assert cfg1.language == "zh"

        ConfigManager.set_config_path(p2)
        cfg2 = ConfigManager.get()
        assert cfg2.language == "en"

    def test_get_config_path_fallback(self, tmp_path, monkeypatch):
        """get_config_path() should fall back to env var then default."""
        # No instance path set
        assert ConfigManager.get_config_path() is not None  # falls to default

        # Env var fallback
        env_path = str(tmp_path / "env.json")
        monkeypatch.setenv("BUILDERPULSE_CONFIG_PATH", env_path)
        assert ConfigManager.get_config_path() == env_path

    def test_get_config_path_instance_takes_priority(self, tmp_path, monkeypatch):
        """Instance path should take priority over env var."""
        instance = tmp_path / "instance.json"
        env_path = str(tmp_path / "env.json")
        monkeypatch.setenv("BUILDERPULSE_CONFIG_PATH", env_path)

        ConfigManager.set_config_path(instance)
        assert ConfigManager.get_config_path() == str(instance)
