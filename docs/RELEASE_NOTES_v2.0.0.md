# BuilderPulse v2.0.0 — Release Notes

**Release date:** 2026-06-04
**Status:** Stable
**Python:** >= 3.9

## Headline

v2.0.0 turns BuilderPulse from "two separate tools" into a single composable pipeline. The plugin system, batch manager, and observability layer are the three biggest additions — they unlock a category of use cases (long-running digest jobs, custom channel integrations, production monitoring) that weren't possible in v1.

## What's New

### Plugin System (entry-point based)
Drop a new downloader, source, or channel into `pyproject.toml` under `[project.entry-points."builderpulse.*"]` and it shows up in `bp` automatically. Fault-tolerant lazy loading — one bad plugin can't take down the rest.

### Batch Manager + Caching
Resumable batch jobs with SQLite-backed cache (WAL mode), token-bucket rate limiter, disk-space guard, and concurrency semaphore. Restart mid-batch without re-processing what's already done.

### Observability
OpenTelemetry integration with graceful no-op stubs when OTel isn't installed. Tracer, meter, and async context helpers ready to wire into your existing observability stack.

### MCP Server (8 tools)
Full JSON-RPC 2.0 server over stdio. Works with Claude Code, Cursor, Continue — any MCP-compatible agent. Tools: `transcribe`, `batch_transcribe`, `digest`, `process`, `fetch_feed`, `list_sources`, `config`, `reload_config`.

### New Sources
- **YouTube channels** via RSS
- **Bilibili users** with WBI signing
- **Blog date filtering**

### Reliability
- Retry with exponential backoff (sync + async), transient-only
- ConfigManager with thread-safe singleton, hot-reload, file permission checks
- 15 typed error codes + plugin code registration
- Log sanitization (auto-redacts sensitive values)

## Upgrade from v1

```bash
pip install --upgrade builderpulse
```

**Breaking changes:** none at the CLI level. v1 commands work unchanged. If you import the Python API directly, see [MIGRATION.md](MIGRATION.md).

## Stats

- **449 tests** passing
- **23 tasks** delivered across 4 sprints
- **Pure Python** — no Node.js dependency
- Cross-platform: Windows, macOS, Linux

## Known Limitations

- Faster-whisper tests skip without env+deps (documented in test config)
- X/Twitter API v2 access requires paid tier ($100/mo); Nitter RSS fallback provided

## Thanks

To everyone who filed issues, tested pre-releases, and contributed feedback during the v2 cycle.

---

**Install:** `pip install builderpulse`
**Quick start:** `bp digest --lang zh --deliver telegram`
**Docs:** [README](../README.md) | [中文](../README.zh-CN.md)
