"""Tests for builderpulse.infra.agent_output."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from builderpulse.infra.agent_output import AgentOutput


class TestAgentOutput:
    def test_schema_version_default(self):
        out = AgentOutput(
            config={},
            results=[],
            errors=[],
            stats={},
        )
        assert out.schema_version == "builderpulse.agent-output/v2"

    def test_generated_at_auto_set(self):
        out = AgentOutput(config={}, results=[], errors=[], stats={})
        assert isinstance(out.generated_at, datetime)

    def test_config_sanitizes_key(self):
        out = AgentOutput(
            config={"api_key": "sk-secret123", "safe": "ok"},
            results=[],
            errors=[],
            stats={},
        )
        assert out.config["api_key"] == "***REDACTED***"
        assert out.config["safe"] == "ok"

    def test_config_sanitizes_secret(self):
        out = AgentOutput(
            config={"client_secret": "abc", "normal": 1},
            results=[],
            errors=[],
            stats={},
        )
        assert out.config["client_secret"] == "***REDACTED***"
        assert out.config["normal"] == 1

    def test_config_sanitizes_token(self):
        out = AgentOutput(
            config={"access_token": "tok_123"},
            results=[],
            errors=[],
            stats={},
        )
        assert out.config["access_token"] == "***REDACTED***"

    def test_config_sanitizes_password(self):
        out = AgentOutput(
            config={"password": "hunter2"},
            results=[],
            errors=[],
            stats={},
        )
        assert out.config["password"] == "***REDACTED***"

    def test_config_no_false_positive(self):
        """Keys that merely *contain* 'key' as a substring but not as a
        sensitive keyword should not be redacted."""
        out = AgentOutput(
            config={"monkey": "ape", "keyboard": "qwerty"},
            results=[],
            errors=[],
            stats={},
        )
        # 'monkey' contains 'key' but shouldn't be redacted
        assert out.config["monkey"] == "ape"
        assert out.config["keyboard"] == "qwerty"

    def test_to_json_roundtrip(self):
        out = AgentOutput(
            config={"a": 1},
            results=[{"id": 1}],
            errors=[],
            stats={"total": 1},
        )
        j = out.to_json()
        data = json.loads(j)
        assert data["schema_version"] == "builderpulse.agent-output/v2"
        assert data["results"] == [{"id": 1}]
        assert data["config"]["a"] == 1

    def test_to_mcp_content(self):
        out = AgentOutput(
            config={},
            results=[{"ok": True}],
            errors=[],
            stats={},
        )
        mcp = out.to_mcp_content()
        assert mcp["type"] == "text"
        assert mcp["mimeType"] == "application/json"
        payload = json.loads(mcp["text"])
        assert payload["results"] == [{"ok": True}]

    def test_json_encoders_datetime(self):
        now = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
        out = AgentOutput(
            generated_at=now,
            config={},
            results=[],
            errors=[],
            stats={},
        )
        j = out.to_json()
        assert "2026-06-04" in j

    def test_json_encoders_path(self):
        out = AgentOutput(
            config={"path": Path("/tmp/test")},
            results=[],
            errors=[],
            stats={},
        )
        j = out.to_json()
        data = json.loads(j)
        assert data["config"]["path"] == str(Path("/tmp/test"))

    def test_json_encoders_exception(self):
        out = AgentOutput(
            config={},
            results=[],
            errors=[{"error": ValueError("bad input")}],
            stats={},
        )
        j = out.to_json()
        data = json.loads(j)
        assert "bad input" in data["errors"][0]["error"]
