"""Tests for MCP-aware logger."""
import os
import sys
from io import StringIO
from unittest.mock import patch

from builderpulse.infra.logger import get_logger, is_mcp_mode

def test_logger_creation():
    logger = get_logger("test")
    assert logger.name == "builderpulse.test"

def test_logger_singleton():
    l1 = get_logger("singleton_test")
    l2 = get_logger("singleton_test")
    assert l1 is l2

def test_is_mcp_mode_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BUILDERPULSE_MODE", None)
        assert not is_mcp_mode()

def test_is_mcp_mode_enabled():
    with patch.dict(os.environ, {"BUILDERPULSE_MODE": "mcp"}):
        assert is_mcp_mode()

def test_mcp_mode_output_to_stderr(capfd):
    """In MCP mode, log output should go to stderr, not stdout."""
    with patch.dict(os.environ, {"BUILDERPULSE_MODE": "mcp"}):
        # Clear cached loggers
        from builderpulse.infra import logger as logger_mod
        logger_mod._LOGGERS.clear()

        log = get_logger("mcp_test")
        log.info("test message")

        captured = capfd.readouterr()
        assert "test message" in captured.err
        # stdout should be clean (no log output)
        assert "test message" not in captured.out
