"""MCP-aware logger. All output goes to stderr in MCP mode."""

import logging
import os
import re
import sys
import threading

_LOGGERS: dict[str, logging.Logger] = {}
_LOGGER_LOCK = threading.Lock()


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger. Respects BUILDERPULSE_MODE env var.

    Thread-safe: uses double-checked locking to avoid races on _LOGGERS dict.
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    with _LOGGER_LOCK:
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

        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        _LOGGERS[name] = logger
        return logger


def is_mcp_mode() -> bool:
    """Check if running in MCP mode."""
    return os.environ.get("BUILDERPULSE_MODE", "cli").lower() == "mcp"


class SensitiveDataFilter(logging.Filter):
    """Global log filter that redacts API keys, cookies, and WBI params.

    Uses a fast-path: if the message contains none of the SENSITIVE_KEYWORDS,
    skip regex processing entirely.

    NOTE: This filter is **one-shot** and not stackable. Each LogRecord is
    marked on first processing so subsequent filter passes (e.g. when filters
    are stacked) short-circuit. This prevents cumulative in-place mutation
    of ``record.msg`` when multiple SensitiveDataFilter instances share the
    same record.
    """

    SENSITIVE_KEYWORDS = [
        "w_rid",
        "wts",
        "sessdata",
        "api_key",
        "token",
        "secret",
    ]

    # Marker attribute on LogRecord.__dict__ to prevent re-redaction.
    _REDACTED_ATTR = "_bp_sensitive_redacted"

    # Pre-compiled regex: matches param=value pairs for sensitive names
    _URL_PARAM_RE = re.compile(
        r"(w_rid|wts|sessdata|api_key|token|secret)"
        r"=([^&\s\"']+)",
        re.IGNORECASE,
    )

    # Matches sensitive keys in JSON strings: "key": "value" or "key":"value"
    _JSON_FIELD_RE = re.compile(
        r'"(w_rid|wts|sessdata|api_key|token|secret)"'
        r'\s*:\s*"([^"]*)"',
        re.IGNORECASE,
    )

    def filter(self, record: logging.LogRecord) -> bool:
        # Idempotency guard: skip records already processed by this filter.
        if getattr(record, self._REDACTED_ATTR, False):
            return True

        msg = record.getMessage()
        if not isinstance(msg, str):
            return True

        # Fast-path: skip if no sensitive keyword present
        if not any(kw in msg.lower() for kw in self.SENSITIVE_KEYWORDS):
            return True

        # Build a NEW redacted string and assign to record.msg.
        # Assigning to record.msg is the documented logging.Filter contract
        # for mutating the rendered message; we just guard against repeated
        # application via the marker above.
        redacted = self._redact_url(msg)
        redacted = self._redact_json(redacted)
        record.msg = redacted
        record.args = None
        setattr(record, self._REDACTED_ATTR, True)
        return True

    @staticmethod
    def _redact_url(text: str) -> str:
        return SensitiveDataFilter._URL_PARAM_RE.sub(
            lambda m: f"{m.group(1)}=***", text
        )

    @staticmethod
    def _redact_json(text: str) -> str:
        return SensitiveDataFilter._JSON_FIELD_RE.sub(
            lambda m: f'"{m.group(1)}": "***"', text
        )


# Register filter at module level so it's active when logger is imported
logging.getLogger().addFilter(SensitiveDataFilter())
