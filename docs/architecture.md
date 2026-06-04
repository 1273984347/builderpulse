# BuilderPulse Architecture

## Module Diagram

```
builderpulse/
  cli.py                  # Click CLI (bp command)
  mcp_server.py           # MCP JSON-RPC server (stdio)
  migrate.py              # v1 → v2 config migration
  core/
    config.py             # Config dataclass + env overrides
    config_manager.py     # Thread-safe singleton + hot-reload
    models.py             # SourceRef, FeedItem, Transcript
    pipeline.py           # Step-based pipeline (sync)
    error_codes.py        # ErrorCode enum + plugin registry
    state.py              # Dedup state (SQLite)
    shared_utils.py       # WBI signing, common helpers
  sources/
    podcast.py            # RSS feed source
    twitter.py            # X/Twitter source
    blog.py               # Blog scraping source
    bilibili.py           # Bilibili video source
    youtube.py            # YouTube RSS source
  engines/
    whisper.py            # OpenAI Whisper engine
    whisperx.py           # WhisperX engine
    faster_whisper.py     # faster-whisper engine
  batch/
    manager.py            # BatchManager orchestrator
    cache.py              # SQLite result cache (WAL mode)
    retry.py              # Sync/async retry with backoff
    rate_limiter.py       # Token-bucket rate limiter
    disk_guard.py         # Disk space guard
  deliver/
    telegram.py           # Telegram delivery
    email.py              # Email (SMTP) delivery
    lark.py               # Lark/Feishu delivery
    dingtalk.py           # DingTalk delivery
    discord.py            # Discord webhook delivery
  remix/
    remix.py              # LLM summarization/translation
  plugins/
    registry.py           # Plugin registry (entry_points)
  infra/
    observability.py      # OpenTelemetry integration
    performance.py        # Timing/profiling utilities
    agent_output.py       # Pydantic models for MCP output
    progress.py           # Rich progress rendering
  prompts/
    *.md                  # LLM prompt templates
```

## Data Flow

```
URL/Feed
  │
  ▼
SourceRef.from_url()          ← Parse URL → source_type + native_id
  │
  ▼
Pipeline
  ├── step_download           ← DownloaderPlugin / yt-dlp
  ├── step_transcribe         ← Engine auto-select (faster-whisper → whisper → whisperx)
  ├── step_summarize          ← LLM remix (Claude/GPT/Ollama)
  └── step_deliver(channel)   ← ChannelPlugin / built-in deliver/
  │
  ▼
PipelineContext
  ├── .transcript: Transcript
  ├── .summary: str
  ├── .error: str | None
  └── .delivery_results: dict
```

## Sync / Async Boundary

BuilderPulse uses a **sync-first** architecture for CLI and MCP compatibility:

| Layer | Mode | Rationale |
|:------|:-----|:----------|
| CLI (`cli.py`) | Sync | Click is synchronous; avoids asyncio.run() issues on Windows |
| MCP server | Sync (stdio read loop) | MCP protocol is request/response; no concurrency needed |
| Pipeline | Sync | Sequential steps; no parallelism within a single URL |
| BatchManager | Sync API + Async option | `process_batch()` is sync; `process_batch_async()` uses asyncio for concurrency |
| RateLimiter | Async | Token-bucket naturally fits asyncio.Lock |
| DiskGuard | Sync + Async option | `check()` is sync; `wait_for_space_async()` for batch use |

The batch layer bridges sync and async:
- `BatchManager.process_batch()` iterates URLs synchronously (CLI path)
- `BatchManager.process_batch_async()` uses `asyncio.gather()` with semaphore + rate limiter (programmatic path)

## Configuration Precedence

```
1. Environment variables (BUILDERPULSE_*)
2. JSON file (~/.builderpulse/config.json)
3. Field defaults in Config dataclass
```

`ConfigManager` provides thread-safe singleton access with hot-reload and subscriber notifications.

## Plugin System

Plugins are discovered via Python entry_points (lazy, fault-tolerant):

```
entry_points:
  builderpulse.downloaders → DownloaderPlugin Protocol
  builderpulse.sources     → SourcePlugin Protocol
  builderpulse.channels    → ChannelPlugin Protocol
```

Runtime registration is also supported via `PluginRegistry.register_group()`.
