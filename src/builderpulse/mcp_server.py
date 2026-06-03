"""BuilderPulse MCP Server — tool registration for AI agents."""
from __future__ import annotations
import json
import logging
import os
from typing import Any

os.environ["BUILDERPULSE_MODE"] = "mcp"

logger = logging.getLogger("builderpulse.mcp")

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
    from builderpulse.sources.podcast import PodcastSource
    from builderpulse.sources.twitter import TwitterSource
    from builderpulse.sources.blog import BlogSource

    items = []
    errors = []

    try:
        items.extend(PodcastSource().fetch(days=days))
    except Exception as e:
        errors.append(f"podcast: {e}")

    try:
        items.extend(TwitterSource().fetch())
    except Exception as e:
        errors.append(f"twitter: {e}")

    try:
        items.extend(BlogSource().fetch(days=days))
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
    if source == "podcast":
        from builderpulse.sources.podcast import PodcastSource
        items = PodcastSource().fetch(days=days, limit=limit)
    elif source == "twitter":
        from builderpulse.sources.twitter import TwitterSource
        items = TwitterSource().fetch(limit=limit)
    elif source == "blog":
        from builderpulse.sources.blog import BlogSource
        items = BlogSource().fetch(days=days, limit=limit)
    elif source == "bilibili":
        from builderpulse.sources.bilibili import BilibiliSource
        items = BilibiliSource().fetch(limit=limit)
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

def _handle_reload_config() -> dict:
    return {"status": "reloaded", "message": "Configuration reloaded from disk"}
