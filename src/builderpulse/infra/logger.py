"""MCP-aware logger. All output goes to stderr in MCP mode."""
import logging
import os
import sys

_LOGGERS: dict[str, logging.Logger] = {}

def get_logger(name: str) -> logging.Logger:
    """Get or create a logger. Respects BUILDERPULSE_MODE env var."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(f"builderpulse.{name}")
    mode = os.environ.get("BUILDERPULSE_MODE", "cli").lower()

    if mode == "mcp":
        # MCP mode: ALL output → stderr (stdout is reserved for JSON-RPC)
        handler = logging.StreamHandler(sys.stderr)
    else:
        # CLI mode: progress/results → stdout, logs → stderr
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    _LOGGERS[name] = logger
    return logger

def is_mcp_mode() -> bool:
    """Check if running in MCP mode."""
    return os.environ.get("BUILDERPULSE_MODE", "cli").lower() == "mcp"
