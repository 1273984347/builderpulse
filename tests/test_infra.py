"""Tests for infrastructure modules."""
from builderpulse.infra.i18n import t, set_language, get_language
from builderpulse.infra.security import is_safe_url, sanitize_filename
from builderpulse.infra.platform_compat import find_ffmpeg, get_config_dir, is_windows
from builderpulse.infra.progress import ProgressReporter

def test_i18n_english():
    set_language("en")
    assert "Downloading" in t("download_start", url="test")

def test_i18n_chinese():
    set_language("zh")
    assert "下载" in t("download_start", url="test")
    set_language("en")  # reset

def test_i18n_missing_key():
    set_language("en")
    assert t("nonexistent_key", default="fallback") == "fallback"

def test_safe_url():
    assert is_safe_url("https://www.youtube.com/watch?v=abc")
    assert is_safe_url("https://bilibili.com/video/BV123")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("file:///etc/passwd")

def test_sanitize_filename():
    assert sanitize_filename('hello<>world') == "hello__world"
    assert sanitize_filename("  spaces  ") == "spaces"
    assert sanitize_filename("a" * 300, max_len=50) == "a" * 50

def test_find_ffmpeg():
    # May or may not be installed
    result = find_ffmpeg()
    # Just verify it returns a string or None
    assert result is None or isinstance(result, str)

def test_config_dir():
    d = get_config_dir()
    assert d.name == ".builderpulse"

def test_progress_reporter():
    with ProgressReporter(total=10, desc="test") as p:
        p.update(5)
        assert p.percent == 50.0
        p.update(5)
        assert p.percent == 100.0
