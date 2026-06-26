"""BuilderPulse MCP Server — real JSON-RPC over stdio for AI agents.

Implements MCP protocol (tools/list + tools/call) without external SDK dependency.
Compatible with Claude Code, Cursor, Continue, and any MCP client.
"""

from __future__ import annotations
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("builderpulse.mcp")

# ── MCP Protocol ────────────────────────────────────────────────


def _make_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_error(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def run_mcp_server() -> None:
    """Run MCP server over stdio (JSON-RPC 2.0). Synchronous for Windows compatibility."""
    os.environ["BUILDERPULSE_MODE"] = "mcp"

    # Use binary mode for stdin/stdout to handle Content-Length framing
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    def read_message() -> dict | None:
        """Read a single JSON-RPC message from stdin."""
        # Read Content-Length header
        _MAX_HEADER_LINE = 4096
        header_line = b""
        while True:
            byte = stdin.read(1)
            if not byte:
                return None
            header_line += byte
            if len(header_line) > _MAX_HEADER_LINE:
                raise ValueError("Header line too long")
            if header_line.endswith(b"\r\n"):
                break

        header_line = header_line.decode("utf-8").strip()
        if not header_line.startswith("Content-Length:"):
            # Try parsing as raw JSON
            try:
                return json.loads(header_line)
            except json.JSONDecodeError:
                return None

        try:
            length = int(header_line.split(":")[1].strip())
        except (ValueError, IndexError):
            return None
        # P1 fix: validate Content-Length bounds
        if length < 0 or length > 10 * 1024 * 1024:  # 10MB cap
            return None
        # Read the empty line after header
        stdin.readline()
        # P1 fix: handle partial reads
        body = b""
        while len(body) < length:
            chunk = stdin.read(length - len(body))
            if not chunk:
                break
            body += chunk
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
                response = _make_response(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "builderpulse", "version": "2.0.0"},
                    },
                )
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                response = _make_response(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = handle_tool_call(tool_name, arguments)
                response = _make_response(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False),
                            }
                        ]
                    },
                )
            elif method == "ping":
                response = _make_response(request_id, {})
            else:
                response = _make_error(
                    request_id, -32601, f"Method not found: {method}"
                )

            write_message(response)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON: %s", e)
            write_message(_make_error(None, -32700, f"Parse error: {e}"))
            continue
        except Exception as e:
            logger.error("Server error: %s", e)
            break


def main():
    """Entry point for `builderpulse-mcp` command."""
    run_mcp_server()  # P0 fix: sync function, no asyncio.run()


# ── Tool definitions ────────────────────────────────────────────

TOOLS = [
    {
        "name": "bp_transcribe",
        "description": "Transcribe video/audio URL to text. Supports B站/抖音/YouTube/1000+ sites.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Video/audio URL or local file path",
                },
                "engine": {
                    "type": "string",
                    "enum": ["auto", "whisper", "whisperx", "faster-whisper"],
                    "default": "auto",
                },
                "language": {
                    "type": "string",
                    "enum": ["zh", "en", "auto"],
                    "default": "auto",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "text", "json"],
                    "default": "markdown",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "bp_digest",
        "description": "Generate AI builder digest. Aggregates X/Twitter, podcasts, blogs, Bilibili.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "string",
                    "default": "all",
                    "description": "Comma-separated source names or 'all'",
                },
                "language": {
                    "type": "string",
                    "enum": ["zh", "en", "bilingual"],
                    "default": "zh",
                },
                "days": {"type": "integer", "default": 1},
                "deliver": {
                    "type": "string",
                    "description": "Delivery channels (comma-separated)",
                },
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
                "pipeline": {
                    "type": "string",
                    "default": "transcribe",
                    "description": "Steps: transcribe,summarize,translate,deliver=CHANNEL",
                },
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
                "source": {
                    "type": "string",
                    "enum": ["twitter", "podcast", "blog", "bilibili", "youtube"],
                },
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
        "description": "View BuilderPulse configuration. Sensitive keys are masked.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "show"]},
                "key": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "bp_search_similar",
        "description": "Search similar content using RAG (Qdrant vector search). Returns top-k similar documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "top_k": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of results to return",
                },
                "collection": {
                    "type": "string",
                    "default": "builderpulse",
                    "description": "Qdrant collection name",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "bp_generate_response",
        "description": "Generate AI response using LLM (Claude/OpenAI/Ollama). Supports system prompt + context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "User prompt",
                },
                "system": {
                    "type": "string",
                    "default": "",
                    "description": "System prompt (optional)",
                },
                "context": {
                    "type": "string",
                    "default": "",
                    "description": "RAG context (optional, from bp_search_similar)",
                },
                "model": {
                    "type": "string",
                    "default": "auto",
                    "description": "LLM model (auto/claude-sonnet-4-6/gpt-4/ollama/...)",
                },
                "max_tokens": {
                    "type": "integer",
                    "default": 1024,
                    "description": "Max output tokens",
                },
            },
            "required": ["prompt"],
        },
    },
]

# ── Tool handlers ───────────────────────────────────────────────


def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch tool call to appropriate handler."""
    handlers = {
        "bp_transcribe": _handle_transcribe,
        "bp_digest": _handle_digest,
        "bp_process": _handle_process,
        "bp_fetch_feed": _handle_fetch_feed,
        "bp_list_sources": _handle_list_sources,
        "bp_config": _handle_config,
        "bp_search_similar": _handle_search_similar,
        "bp_generate_response": _handle_generate_response,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return handler(**arguments)
    except TypeError as e:
        logger.error("Tool %s invalid arguments: %s", tool_name, e)
        return {"error": f"Invalid arguments: {e}"}
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return {"error": "Internal tool error. Check server logs for details."}


def _handle_transcribe(
    url: str,
    engine: str = "auto",
    language: str = "auto",
    output_format: str = "markdown",
) -> dict:
    from builderpulse.infra.security import is_safe_url

    if not is_safe_url(url):
        return {"error": f"URL not allowed: {url}"}

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


def _handle_digest(
    sources: str = "all", language: str = "zh", days: int = 1, deliver: str = None
) -> dict:
    from builderpulse.core.config_manager import ConfigManager

    # P2 fix (H4): delegate fetching to the shared aggregator so CLI and
    # MCP code paths don't drift.
    from builderpulse.core.source_aggregator import fetch_all_sources

    cfg = ConfigManager.get_raw()
    items, errors = fetch_all_sources(cfg, days=days, sources=sources, skip_failed=True)

    result = {
        "item_count": len(items),
        "items": [
            {"title": i.title, "url": i.url, "source": i.source_type}
            for i in items[:20]
        ],
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


def _handle_process(
    url: str, pipeline: str = "transcribe", deliver: str = None
) -> dict:
    from builderpulse.infra.security import is_safe_url

    if not is_safe_url(url):
        return {"error": f"URL not allowed: {url}"}

    # Session 33: 修 mcp_server Pipeline 不传 config 跟 cli.py:306 同根因
    # 角色 LLM 抽象 (S31 M1) 需 Config 才能走 get_role_provider (EXTRACT/TRANSLATE)
    # E82 (S21 active: 控制器不实测) 同类 — 5 调用点 4 个已修, 这是最后 1 个
    from builderpulse.core.config import Config
    from builderpulse.core.config_manager import ConfigManager
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import (
        Pipeline,
        step_download,
        step_transcribe,
        step_summarize,
        step_deliver,
    )

    # 优先从 ConfigManager 拿 role_llm_model_map (跟 MCP 调用方统一配置)
    # fallback 到 default Config 让 role_llm_registry 走 DEFAULT_ROLE_SPECS
    try:
        cfg = ConfigManager.get()
    except Exception:
        cfg = Config()
    cfg_role_map = getattr(cfg, "role_llm_model_map", None) or {}
    role_cfg = Config(role_llm_model_map=cfg_role_map) if cfg_role_map else Config()

    source = SourceRef.from_url(url)
    p = Pipeline(config=role_cfg)

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
    from builderpulse.core.config_manager import ConfigManager

    cfg = ConfigManager.get_raw()

    src = None
    try:
        if source == "podcast":
            from builderpulse.sources.podcast import PodcastSource

            feeds = cfg.get("sources", {}).get("podcast", {}).get("feeds", [])
            src = PodcastSource(feeds=feeds)
            items = src.fetch(days=days, limit=limit)
        elif source == "twitter":
            from builderpulse.sources.twitter import TwitterSource

            accounts = cfg.get("sources", {}).get("twitter", {}).get("accounts", [])
            src = TwitterSource(accounts=accounts)
            items = src.fetch(limit=limit)
        elif source == "blog":
            from builderpulse.sources.blog import BlogSource

            urls = cfg.get("sources", {}).get("blog", {}).get("urls", [])
            src = BlogSource(urls=urls)
            items = src.fetch(days=days, limit=limit)
        elif source == "bilibili":
            from builderpulse.sources.bilibili import BilibiliSource

            users = cfg.get("sources", {}).get("bilibili", {}).get("users", [])
            src = BilibiliSource(users=users)
            items = src.fetch(limit=limit)
        elif source == "youtube":
            from builderpulse.sources.youtube import YouTubeSource

            src = YouTubeSource()
            items = src.fetch(limit=limit)
        else:
            return {"error": f"Unknown source: {source}"}
    finally:
        if src is not None:
            src.close()

    return {
        "items": [
            {"title": i.title, "url": i.url, "content": i.content[:200]} for i in items
        ]
    }


def _handle_list_sources() -> dict:
    return {
        "sources": ["twitter", "podcast", "blog", "bilibili", "youtube"],
        "delivery_channels": [
            "telegram",
            "email",
            "lark",
            "dingtalk",
            "discord",
            "wecom",
            "wechat",
            "stderr",
        ],
    }


def _handle_config(action: str, key: str = None, value: str = None) -> dict:
    from builderpulse.core.config import Config

    cfg = Config()

    if action == "show":
        return cfg.to_dict(mask_secrets=True)
    elif action == "get" and key:
        # P0 fix: block access to sensitive keys via get
        if Config._is_sensitive(key):
            return {
                "error": f"Key '{key}' is sensitive. Use 'show' with mask_secrets=True."
            }
        return {"key": key, "value": getattr(cfg, key, None)}
    elif action == "set":
        return {
            "error": "Config 'set' not supported in MCP. "
            "Use environment variables (BUILDERPULSE_*) or edit config.json directly."
        }
    else:
        return {"error": "Invalid config action. Valid actions: get, show."}


def _handle_search_similar(
    query: str, top_k: int = 10, collection: str = "builderpulse"
) -> dict:
    """Search similar content using RAG (Qdrant vector search)."""
    try:
        from builderpulse.rag.channel import RAGChannel

        channel = RAGChannel(collection=collection)
        results = channel.search(query, top_k=top_k)

        return {
            "query": query,
            "result_count": len(results),
            "results": [
                {
                    "id": r["id"],
                    "score": r["score"],
                    "text": r["text"][:500],
                    "metadata": r.get("metadata", {}),
                }
                for r in results
            ],
        }
    except Exception as e:
        return {"error": f"RAG search failed: {e}"}


def _handle_generate_response(
    prompt: str,
    system: str = "",
    context: str = "",
    model: str = "auto",
    max_tokens: int = 1024,
) -> dict:
    """Generate AI response using LLM."""
    try:
        from builderpulse.remix.summarizer import Summarizer

        summarizer = Summarizer(model=model)

        # 构建完整 prompt
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {prompt}"

        response = summarizer.summarize(
            text=full_prompt,
            system_prompt=system or "You are a helpful assistant.",
            max_tokens=max_tokens,
        )

        return {
            "response": response,
            "model": model,
            "prompt_tokens": len(prompt.split()),
            "max_tokens": max_tokens,
        }
    except Exception as e:
        return {"error": f"LLM generation failed: {e}"}
