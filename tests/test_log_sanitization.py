"""Tests for SensitiveDataFilter in logger.py."""
import logging

from builderpulse.infra.logger import SensitiveDataFilter


def test_redacts_api_key():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "api_key=sk-1234567890abcdef", (), None)
    f.filter(record)
    assert "sk-1234567890abcdef" not in record.msg
    assert "api_key=" in record.msg


def test_fast_path_no_sensitive_keywords():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "normal message", (), None)
    f.filter(record)
    assert record.msg == "normal message"


def test_redacts_wbi_params():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "url?w_rid=abc123&wts=123456", (), None)
    f.filter(record)
    assert "abc123" not in record.msg
    assert "123456" not in record.msg


def test_redacts_json_fields():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, '{"api_key": "secret123", "name": "test"}', (), None)
    f.filter(record)
    assert "secret123" not in record.msg
    assert '"name": "test"' in record.msg


def test_handles_non_string_msg():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, 42, (), None)
    assert f.filter(record) is True


def test_redacts_sessdata():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "sessdata=abc123def456", (), None)
    f.filter(record)
    assert "abc123def456" not in record.msg
    assert "sessdata=" in record.msg


def test_redacts_token():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "token=my_secret_token_value", (), None)
    f.filter(record)
    assert "my_secret_token_value" not in record.msg
    assert "token=" in record.msg


def test_redacts_secret():
    f = SensitiveDataFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "secret=hunter2", (), None)
    f.filter(record)
    assert "hunter2" not in record.msg
    assert "secret=" in record.msg
