"""Shared test fixtures."""
import os
import pytest

@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Redirect state.db to temp dir for test isolation."""
    monkeypatch.setenv("BUILDERPULSE_STATE_DB", str(tmp_path / "state.db"))
