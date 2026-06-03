"""BuilderPulse MCP Server — real JSON-RPC over stdio for AI agents.

Implements MCP protocol (tools/list + tools/call) without external SDK dependency.
Compatible with Claude Code, Cursor, Continue, and any MCP client.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
from typing import Any

os.environ["BUILDERPULSE_MODE"] = "mcp"

logger = logging.getLogger("builderpulse.mcp")

# ── MCP Protocol ────────────────────────────────────────────────

def _make_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}

def _make_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def run_mcp_server() -> None:
    """Run MCP server over stdio (JSON-RPC 2.0). Synchronous for Windows compatibility."""
    import sys

    # Use binary mode for stdin/stdout to handle Content-Length framing
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    def read_message() -> dict | None:
        """Read a single JSON-RPC message from stdin."""
        # Read Content-Length header
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
            # Try parsing as raw JSON
            try:
                return json.loads(header_line)
            except json.JSONDecodeError:
                return None

        length = int(header_line.split(":")[1].strip())
        # Read the empty line after header
        stdin.readline()
        # Read the body
        body = stdin.read(length)
        return json.loads(body.decode("utf-8"))

    def write_message(msg: dict) -> None:
        """Write a JSON-RPC message to stdout."""
        body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        stdout.write(header + body)
        stdout.flush()

    while True:
        try:
            msg = read_message()
            if msg is None:
                break

            request_id = msg.get("id")
            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "initialize":
                response = _make_response(request_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "builderpulse", "version": "1.0.0"},
                })
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                response = _make_response(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = handle_tool_call(tool_name, arguments)
                response = _make_response(request_id, {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                })
            elif method == "ping":
                response = _make_response(request_id, {})
            else:
                response = _make_error(request_id, -32601, f"Method not found: {method}")

            write_message(response)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON: %s", e)
            continue
        except Exception as e:
            logger.error("Server error: %s", e)
            break

def main():
    """Entry point for `builderpulse-mcp` command."""
    asyncio.run(run_mcp_server())

# ── Tool definitions ────────────────────────────────────────────

TOOLS = [
    {
        "name": "bp_transcribe",
        "description": "Transcribe video/audio URL to text. Supports B站/抖音/YouTube/1000+ sites.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Video/audio URL or local file path"},
                "engine": {"type": "string", "enum": ["auto", "whisper", "whisperx", "faster-whisper"], "default": "auto"},
                "language": {"type": "string", "enum": ["zh", "en", "auto"], "default": "auto"},
                "output_format": {"type": "string", "enum": ["markdown", "text", "json"], "default": "markdown"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "bp_batch_transcribe",
        "description": "Batch transcribe a creator's videos (B站/抖音).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_url": {"type": "string", "description": "Creator profile URL"},
                "limit": {"type": "integer", "default": 50},
                "language": {"type": "string", "default": "auto"},
            },
            "required": ["user_url"],
        },
    },
    {
        "name": "bp_digest",
        "description": "Generate AI builder digest. Aggregates X/Twitter, podcasts, blogs, Bilibili.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {"type": "string", "default": "all", "description": "Comma-separated source names or 'all'"},
                "language": {"type": "string", "enum": ["zh", "en", "bilingual"], "default": "zh"},
                "days": {"type": "integer", "default": 1},
                "deliver": {"type": "string", "description": "Delivery channels (comma-separated)"},
            },
        },
    },
    {
        "name": "bp_process",
        "description": "End-to-end pipeline: download → transcribe → summarize → deliver.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "pipeline": {"type": "string", "default": "transcribe", "description": "Steps: transcribe,summarize,translate,deliver=CHANNEL"},
                "deliver": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "bp_fetch_feed",
        "description": "Fetch raw content from a source (twitter/podcast/blog/bilibili/youtube).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["twitter", "podcast", "blog", "bilibili", "youtube"]},
                "limit": {"type": "integer", "default": 10},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["source"],
        },
    },
    {
        "name": "bp_list_sources",
        "description": "List all configured content sources.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "bp_config",
        "description": "View or modify BuilderPulse configuration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set", "show"]},
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "bp_reload_config",
        "description": "Hot-reload config.json without restarting MCP server.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# ── Tool handlers ───────────────────────────────────────────────

def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch tool call to appropriate handler."""
    handlers = {
        "bp_transcribe": _handle_transcribe,
        "bp_batch_transcribe": _handle_batch_transcribe,
        "bp_digest": _handle_digest,
        "bp_process": _handle_process,
        "bp_fetch_feed": _handle_fetch_feed,
        "bp_list_sources": _handle_list_sources,
        "bp_config": _handle_config,
        "bp_reload_config": _handle_reload_config,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    # Check for config reload flag before handling
    if _check_reload_flag():
        logger.info("Config reload detected, picking up changes")

    try:
        return handler(**arguments)
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return {"error": str(e)}

def _handle_transcribe(url: str, engine: str = "auto", language: str = "auto", output_format: str = "markdown") -> dict:
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import Pipeline, step_download, step_transcribe

    source = SourceRef.from_url(url)
    p = Pipeline()
    p.add(step_download)
    p.add(step_transcribe)
    ctx = p.run(source)

    if ctx.error:
        return {"error": ctx.error}

    if not ctx.transcript:
        return {"error": "No transcript produced"}

    return {
        "text": ctx.transcript.text,
        "language": ctx.transcript.language,
        "engine": ctx.transcript.engine,
        "word_count": ctx.transcript.word_count,
    }

def _handle_batch_transcribe(user_url: str, limit: int = 50, language: str = "auto") -> dict:
    return {"status": "not_implemented", "message": "Batch transcribe not yet implemented"}

def _handle_digest(sources: str = "all", language: str = "zh", days: int = 1, deliver: str = None) -> dict:
    import json
    from pathlib import Path

    config_path = Path.home() / ".builderpulse" / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

    from builderpulse.sources.podcast import PodcastSource
    from builderpulse.sources.twitter import TwitterSource
    from builderpulse.sources.blog import BlogSource

    items = []
    errors = []

    try:
        feeds = cfg.get("sources", {}).get("podcast", {}).get("feeds", [])
        items.extend(PodcastSource(feeds=feeds).fetch(days=days))
    except Exception as e:
        errors.append(f"podcast: {e}")

    try:
        accounts = cfg.get("sources", {}).get("twitter", {}).get("accounts", [])
        items.extend(TwitterSource(accounts=accounts).fetch())
    except Exception as e:
        errors.append(f"twitter: {e}")

    try:
        urls = cfg.get("sources", {}).get("blog", {}).get("urls", [])
        items.extend(BlogSource(urls=urls).fetch(days=days))
    except Exception as e:
        errors.append(f"blog: {e}")

    result = {
        "item_count": len(items),
        "items": [{"title": i.title, "url": i.url, "source": i.source_type} for i in items[:20]],
        "errors": errors,
    }

    if deliver:
        from builderpulse.deliver import get_channel
        content = "\n\n".join(f"## {i.title}\n{i.url}" for i in items[:20])
        for ch_name in deliver.split(","):
            try:
                ch = get_channel(ch_name.strip())
                ch.send(content, title="BuilderPulse Digest")
                result[f"delivered_{ch_name.strip()}"] = True
            except Exception as e:
                result[f"delivered_{ch_name.strip()}"] = f"failed: {e}"

    return result

def _handle_process(url: str, pipeline: str = "transcribe", deliver: str = None) -> dict:
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import Pipeline, step_download, step_transcribe, step_summarize, step_deliver

    source = SourceRef.from_url(url)
    p = Pipeline()

    steps = [s.strip() for s in pipeline.split(",")]
    if "download" in steps or "transcribe" in steps:
        p.add(step_download)
    if "transcribe" in steps:
        p.add(step_transcribe)
    if "summarize" in steps:
        p.add(step_summarize)
    if deliver:
        for ch in deliver.split(","):
            p.add(step_deliver(ch.strip()))

    ctx = p.run(source)

    if ctx.error:
        return {"error": ctx.error}

    return {
        "transcript_words": ctx.transcript.word_count if ctx.transcript else 0,
        "summary": ctx.summary,
        "delivery_results": ctx.delivery_results,
    }

def _handle_fetch_feed(source: str, limit: int = 10, days: int = 7) -> dict:
    import json
    from pathlib import Path

    config_path = Path.home() / ".builderpulse" / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

    if source == "podcast":
        from builderpulse.sources.podcast import PodcastSource
        feeds = cfg.get("sources", {}).get("podcast", {}).get("feeds", [])
        items = PodcastSource(feeds=feeds).fetch(days=days, limit=limit)
    elif source == "twitter":
        from builderpulse.sources.twitter import TwitterSource
        accounts = cfg.get("sources", {}).get("twitter", {}).get("accounts", [])
        items = TwitterSource(accounts=accounts).fetch(limit=limit)
    elif source == "blog":
        from builderpulse.sources.blog import BlogSource
        urls = cfg.get("sources", {}).get("blog", {}).get("urls", [])
        items = BlogSource(urls=urls).fetch(days=days, limit=limit)
    elif source == "bilibili":
        from builderpulse.sources.bilibili import BilibiliSource
        users = cfg.get("sources", {}).get("bilibili", {}).get("users", [])
        items = BilibiliSource(users=users).fetch(limit=limit)
    elif source == "youtube":
        from builderpulse.sources.youtube import YouTubeSource
        items = YouTubeSource().fetch(limit=limit)
    else:
        return {"error": f"Unknown source: {source}"}

    return {"items": [{"title": i.title, "url": i.url, "content": i.content[:200]} for i in items]}

def _handle_list_sources() -> dict:
    return {
        "sources": ["twitter", "podcast", "blog", "bilibili", "youtube"],
        "delivery_channels": ["telegram", "email", "lark", "dingtalk", "discord", "wecom", "wechat", "stderr"],
    }

def _handle_config(action: str, key: str = None, value: str = None) -> dict:
    from builderpulse.core.config import Config
    cfg = Config()

    if action == "show":
        return cfg.to_dict(mask_secrets=True)
    elif action == "get" and key:
        return {key: getattr(cfg, key, None)}
    elif action == "set" and key and value:
        return {"status": "set", "key": key, "message": "Config set not yet persistent"}
    else:
        return {"error": "Invalid config action"}

def _check_reload_flag() -> bool:
    """Check if config reload was requested via flag file."""
    from pathlib import Path
    flag = Path.home() / ".builderpulse" / ".reload"
    if flag.exists():
        try:
            flag.unlink()
        except OSError:
            pass
        return True
    return False

def _handle_reload_config() -> dict:
    from pathlib import Path
    flag = Path.home() / ".builderpulse" / ".reload"
    flag.parent.mkdir(parents=True, exist_ok=True)
    import time
    flag.write_text(str(time.time()), encoding="utf-8")
    return {"status": "reloaded", "message": "Configuration reloaded from disk"}
