"""Cross-platform compatibility helpers."""

from __future__ import annotations
import shutil
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def find_ffmpeg() -> str | None:
    """Find ffmpeg binary path."""
    return shutil.which("ffmpeg")


def get_config_dir() -> Path:
    """Get the config directory path."""
    return Path.home() / ".builderpulse"


def safe_filename(name: str) -> str:
    """Create a safe filename across platforms."""
    from .security import sanitize_filename

    return sanitize_filename(name)
