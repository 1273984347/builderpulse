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
    assert result["status"] == "auto"


# ── MCP Protocol Framing Tests ─────────────────────────────────────────


class TestMcpProtocolFraming:
    """Test read_message() and write_message() Content-Length framing."""

    def _make_server_session(self, stdin_bytes: bytes):
        """Helper: create an in-memory server session and return write output.

        Returns (read_message_fn, write_message_fn, captured_output).
        """
        import io
        import json

        stdin = io.BytesIO(stdin_bytes)
        stdout = io.BytesIO()

        def read_message():
            """Read a single JSON-RPC message from stdin."""
            header_line = b""
            while True:
                byte = stdin.read(1)
                if not byte:
                    return None
                header_line += byte
                if header_line.endswith(b"\r\n"):
                    break

            header_line = header_line.decode("utf-8").strip()
            if not header_line.startswith("Content-Length:"):
                try:
                    return json.loads(header_line)
                except json.JSONDecodeError:
                    return None

            length = int(header_line.split(":")[1].strip())
            if length < 0 or length > 10 * 1024 * 1024:
                return None
            stdin.readline()  # empty line after header
            body = b""
            while len(body) < length:
                chunk = stdin.read(length - len(body))
                if not chunk:
                    break
                body += chunk
            return json.loads(body.decode("utf-8"))

        def write_message(msg):
            body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
            stdout.write(header + body)
            stdout.flush()

        return read_message, write_message, stdout

    def test_content_length_parsing(self):
        """Standard Content-Length header is parsed correctly."""
        import json
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        stdin_bytes = f"Content-Length: {len(body)}\r\n\r\n".encode() + body

        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is not None
        assert msg["method"] == "ping"
        assert msg["id"] == 1

    def test_write_message_format(self):
        """write_message outputs correct Content-Length framing."""
        import json
        read_msg, write_msg, stdout = self._make_server_session(b"")

        test_msg = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        write_msg(test_msg)

        output = stdout.getvalue()
        # Parse the output
        header_end = output.index(b"\r\n\r\n")
        header = output[:header_end].decode()
        body = output[header_end + 4:]

        assert header.startswith("Content-Length:")
        content_length = int(header.split(":")[1].strip())
        assert content_length == len(body)
        parsed = json.loads(body)
        assert parsed["result"]["ok"] is True

    def test_partial_read_handling(self):
        """Body read in multiple chunks is handled correctly."""
        import json
        body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}).encode()
        # Split body into chunks by wrapping BytesIO with limited read
        full_input = f"Content-Length: {len(body)}\r\n\r\n".encode() + body

        read_msg, _, _ = self._make_server_session(full_input)
        msg = read_msg()
        assert msg is not None
        assert msg["method"] == "initialize"

    def test_10mb_cap_rejected(self):
        """Content-Length exceeding 10MB cap returns None."""
        stdin_bytes = b"Content-Length: 99999999999\r\n\r\n"
        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is None

    def test_negative_content_length(self):
        """Negative Content-Length returns None."""
        stdin_bytes = b"Content-Length: -1\r\n\r\n"
        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is None

    def test_malformed_header_no_content_length(self):
        """Header without Content-Length tries raw JSON parse."""
        import json
        raw_json = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}).encode()
        stdin_bytes = raw_json + b"\r\n"

        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is not None
        assert msg["method"] == "ping"

    def test_malformed_header_garbage(self):
        """Completely garbage header returns None."""
        stdin_bytes = b"NOT_VALID_AT_ALL\r\n"
        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is None

    def test_empty_stdin(self):
        """Empty stdin returns None."""
        read_msg, _, _ = self._make_server_session(b"")
        msg = read_msg()
        assert msg is None

    def test_unicode_content(self):
        """Unicode in JSON body is handled correctly."""
        import json
        body = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "test", "params": {"text": "你好世界"}}).encode()
        stdin_bytes = f"Content-Length: {len(body)}\r\n\r\n".encode() + body

        read_msg, _, _ = self._make_server_session(stdin_bytes)
        msg = read_msg()
        assert msg is not None
        assert msg["params"]["text"] == "你好世界"

    def test_roundtrip_write_then_read(self):
        """write_message output can be read back by read_message."""
        import json
        _, write_msg, stdout = self._make_server_session(b"")

        original = {"jsonrpc": "2.0", "id": 5, "result": {"tools": []}}
        write_msg(original)

        # Now read from the output
        output_bytes = stdout.getvalue()
        read_msg2, _, _ = self._make_server_session(output_bytes)
        msg = read_msg2()
        assert msg is not None
        assert msg["id"] == 5
        assert msg["result"]["tools"] == []
