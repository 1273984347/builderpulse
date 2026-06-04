"""Tests for builderpulse.infra.progress — Rich and Text progress."""
from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest

from builderpulse.infra.progress import (
    RichProgress,
    TextProgress,
    _format_duration,
    create_progress,
)


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_seconds(self):
        assert _format_duration(30) == "30s"

    def test_minutes(self):
        assert _format_duration(135) == "2m 15s"

    def test_hours(self):
        assert _format_duration(3720) == "1h 2m"

    def test_zero(self):
        assert _format_duration(0) == "0s"


# ---------------------------------------------------------------------------
# TextProgress
# ---------------------------------------------------------------------------

class TestTextProgress:
    def test_basic_usage(self, capsys):
        p = TextProgress(total=10, desc="downloading")
        p.update(3)
        p.update(2)
        assert p.current == 5
        assert p.percent == 50.0

    def test_context_manager(self, capsys):
        with TextProgress(total=5) as p:
            p.update(5)
        assert p.current == 5

    def test_eta(self):
        import time
        p = TextProgress(total=100)
        p._start_time = p._start_time - 10  # pretend 10s elapsed
        p.current = 50
        eta = p.eta_seconds
        assert eta is not None
        assert 9 <= eta <= 11  # ~10s remaining

    def test_desc_update(self):
        p = TextProgress(total=5)
        p.update(1, desc="step 1")
        assert p.desc == "step 1"


# ---------------------------------------------------------------------------
# RichProgress (mock rich to avoid dependency)
# ---------------------------------------------------------------------------

class TestRichProgress:
    def test_import_fallback(self):
        """When rich is not available, RichProgress still works without crashing."""
        p = RichProgress(total=5, desc="test")
        p._start()
        p.update(3)
        p._finish()
        assert p.current == 3


# ---------------------------------------------------------------------------
# create_progress factory
# ---------------------------------------------------------------------------

class TestCreateProgress:
    def test_force_text(self):
        p = create_progress(total=10, force_text=True)
        assert isinstance(p, TextProgress)

    def test_tty_returns_rich(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            p = create_progress(total=10)
            assert isinstance(p, RichProgress)

    def test_non_tty_returns_text(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            p = create_progress(total=10)
            assert isinstance(p, TextProgress)

    def test_percent_property(self):
        p = create_progress(total=20, force_text=True)
        p.update(10)
        assert p.percent == 50.0
