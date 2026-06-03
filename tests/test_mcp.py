"""Tests for MCP server tools."""
from builderpulse.mcp_server import handle_tool_call, TOOLS

def test_tool_registry():
    assert len(TOOLS) == 8
    names = [t["name"] for t in TOOLS]
    assert "bp_transcribe" in names
    assert "bp_digest" in names
    assert "bp_config" in names

def test_list_sources():
    result = handle_tool_call("bp_list_sources", {})
    assert "sources" in result
    assert "podcast" in result["sources"]

def test_config_show():
    result = handle_tool_call("bp_config", {"action": "show"})
    assert "language" in result

def test_unknown_tool():
    result = handle_tool_call("bp_nonexistent", {})
    assert "error" in result

def test_fetch_feed_unknown():
    result = handle_tool_call("bp_fetch_feed", {"source": "nonexistent"})
    assert "error" in result

def test_reload_config():
    result = handle_tool_call("bp_reload_config", {})
    assert result["status"] == "reloaded"
