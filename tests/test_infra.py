"""Tests for infrastructure modules."""

from builderpulse.infra.i18n import t, set_language
from builderpulse.infra.security import is_safe_url, sanitize_filename
from builderpulse.infra.platform_compat import find_ffmpeg, get_config_dir
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
    assert sanitize_filename("hello<>world") == "hello__world"
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


# ── is_safe_url() extended tests ───────────────────────────────────────


class TestIsSafeUrlExtended:
    """Extended tests for is_safe_url()."""

    def test_trusted_domain_youtube(self):
        assert is_safe_url("https://www.youtube.com/watch?v=abc") is True

    def test_trusted_domain_youtu_be(self):
        assert is_safe_url("https://youtu.be/abc123") is True

    def test_trusted_domain_bilibili(self):
        assert is_safe_url("https://bilibili.com/video/BV123") is True

    def test_trusted_domain_douyin(self):
        assert is_safe_url("https://www.douyin.com/video/123") is True

    def test_trusted_domain_twitter(self):
        assert is_safe_url("https://twitter.com/user/status/123") is True

    def test_trusted_domain_x_com(self):
        assert is_safe_url("https://x.com/user/status/123") is True

    def test_trusted_domain_github(self):
        assert is_safe_url("https://github.com/user/repo") is True

    def test_subdomain_of_trusted(self):
        """Subdomain of trusted domain should be allowed."""
        assert is_safe_url("https://api.github.com/repos") is True

    def test_unknown_domain_rejected(self):
        assert is_safe_url("https://evil.example.com/phish") is False

    def test_unknown_domain_similar_name(self):
        """Domain that looks like trusted but isn't."""
        assert is_safe_url("https://youtube.evil.com/watch?v=abc") is False

    def test_javascript_scheme(self):
        assert is_safe_url("javascript:alert(1)") is False

    def test_file_scheme(self):
        assert is_safe_url("file:///etc/passwd") is False

    def test_data_scheme(self):
        assert is_safe_url("data:text/html,<h1>hi</h1>") is False

    def test_ftp_scheme(self):
        assert is_safe_url("ftp://example.com/file") is False

    def test_empty_string(self):
        """Empty URL is handled gracefully."""
        assert is_safe_url("") is False

    def test_url_with_credentials(self):
        """URL with user:pass@host — credentials should not bypass check."""
        assert is_safe_url("https://user:pass@evil.example.com/path") is False

    def test_url_with_credentials_trusted(self):
        """URL with credentials — netloc includes user:pass, so host match fails.

        This documents the current behavior: is_safe_url uses raw netloc,
        so credentials in URL cause host matching to fail.
        """
        # netloc is 'user:pass@github.com', which doesn't match 'github.com'
        assert is_safe_url("https://user:pass@github.com/repo") is False

    def test_url_with_port(self):
        """URL with port — netloc includes port, so host match fails.

        This documents the current behavior: is_safe_url uses raw netloc,
        so port in URL causes host matching to fail.
        """
        # netloc is 'github.com:443', which doesn't match 'github.com'
        assert is_safe_url("https://github.com:443/repo") is False

    def test_url_with_fragment(self):
        """URL with fragment."""
        assert is_safe_url("https://youtube.com/watch?v=abc#t=10") is True

    def test_url_with_query_params(self):
        """URL with query parameters."""
        assert is_safe_url("https://bilibili.com/video/BV123?p=1&t=10") is True

    def test_malformed_url(self):
        """Malformed URL string is handled gracefully."""
        assert is_safe_url("not a url at all") is False

    def test_http_scheme(self):
        """HTTP (non-HTTPS) trusted domain is still safe."""
        assert is_safe_url("http://youtube.com/watch?v=abc") is True

    def test_no_scheme(self):
        """URL without scheme is not safe."""
        assert is_safe_url("youtube.com/watch?v=abc") is False
