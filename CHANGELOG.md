# Changelog

All notable changes to BuilderPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-04

### Added

- **Plugin Registry** — Entry-point-based plugin system with Protocol validation for downloaders, sources, and channels. Fault-tolerant lazy loading; one bad plugin never breaks others.
- **ConfigManager** — Thread-safe singleton with hot-reload, subscriber notifications, file permission checks, and reentrancy protection.
- **Error Codes** — 15 core `ErrorCode` values plus plugin code registration via `register_plugin_code()`. JSON-safe string codes for MCP clients.
- **BatchManager** — Orchestrates batch download/transcribe/summarize with SQLite cache (WAL mode), token-bucket rate limiter, disk space guard, and concurrency semaphore.
- **Retry with Exponential Backoff** — Sync and async versions. Transient failures (ConnectionError, TimeoutError) retried; permanent failures fail fast. Full attempt history in `RetryExhausted`.
- **BatchCache** — SQLite-backed result cache with SHA256 URL hashing, thread-local connections, and automatic WAL checkpoint cleanup.
- **RateLimiter** — Async token-bucket rate limiter with configurable QPS and automatic refill.
- **DiskGuard** — Disk space guard with cached checks and sync/async wait-for-space methods.
- **Observability** — OpenTelemetry integration with no-op stubs when OTel is not installed. Tracer, meter, and async context helpers.
- **Performance Profiling** — Timing utilities for measuring pipeline step durations.
- **Agent Output Models** — Pydantic models for structured MCP tool output.
- **Progress Rendering** — Rich-based progress bars with ETA for batch operations.
- **Bilibili Source** — Fetch videos from Bilibili users with WBI signing.
- **YouTube Source** — Fetch videos from YouTube channels via RSS feeds.
- **Blog Date Filtering** — Filter blog posts by publication date.
- **Log Sanitization** — Automatic redaction of sensitive values in log output.
- **Shared Utilities** — WBI signing, common helpers for Bilibili API.
- **MCP Server** — Full JSON-RPC 2.0 over stdio with 8 tools: transcribe, batch_transcribe, digest, process, fetch_feed, list_sources, config, reload_config.
- **CLI Commands** — `bp transcribe`, `bp batch`, `bp digest`, `bp fetch`, `bp process`, `bp clean`, `bp config` (show/set/reload/init), `bp serve`.

### Changed

- CLI version bumped to 2.0.0.
- `bp config reload` now calls `ConfigManager.reload()` and reports subscriber failures.
- `bp digest` now supports bilibili and youtube sources in addition to podcast, twitter, and blog.
- MCP `_handle_digest` includes bilibili and youtube in source aggregation.

### Fixed

- Config env-var override now resolves `Optional[X]` type annotations correctly.
- MCP Content-Length validation (10MB cap) prevents memory exhaustion.
- MCP partial read handling for large messages.
- Config set uses atomic write (tmp file + os.replace) to prevent corruption.
- Config key validation rejects empty segments.
- Pipeline HTTP status check before JSON parsing (Bilibili source).

## v1.0.0 (2026-06-03)

Initial release. Merges video2text (Python transcription) + follow-builders (content aggregation) into a single tool.

### Features

- **Transcription**: Whisper, WhisperX, faster-whisper with auto-detection
- **Downloaders**: yt-dlp (1000+ sites), Bilibili (WBI signing), Douyin (Playwright)
- **Sources**: Podcast RSS, Blog scraping, X/Twitter (API + Nitter fallback), Bilibili, YouTube
- **LLM Summarization**: OpenAI, Anthropic, Ollama adapters with Map-Reduce chunking
- **Delivery**: Telegram, Email (SMTP), 飞书, 钉钉, Discord, 企业微信, WeChat, stderr
- **CLI**: 8 commands (transcribe, batch, digest, fetch, process, clean, config, serve)
- **MCP Server**: 8 tools for AI agent integration (Claude Code, Cursor)
- **State Management**: SQLite WAL mode, crash recovery, idempotent keys
- **Migration**: from follow-builders and video2text

### Architecture

- Pure Python (no Node.js dependency)
- Composable pipeline with chainable steps
- 3-tier secret storage (keyring → secrets.json → env var)
- Cross-platform (Windows/macOS/Linux)
- 126 tests passing

### Codex Review Fixes

- P1: Cursor regression prevention
- P1: Transactional crash recovery
- P1: TOCTOU elimination in mark_processed
- P2: Batch item status validation
- P2: VACUUM after cleanup
- P2: Per-process State dedup
- P2: WAL autocheckpoint tuning
