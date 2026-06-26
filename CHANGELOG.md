# Changelog

All notable changes to BuilderPulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-06-26 (S2: LightRAG Roles + Source Registry)

### Added (Session 31 M1: LightRAG Role Abstraction)

- **`builderpulse.remix.roles`**: New module (146 行) derived from
  [LightRAG llm_roles.py](https://github.com/HKUDS/LightRAG) — provides
  `Role` enum (EXTRACT/QUERY/KEYWORDS/TRANSLATE), `RoleSpec` dataclass,
  `RoleLLMRegistry`, `DEFAULT_ROLE_SPECS` (4 角色默认配置), and
  `get_role_provider(role, registry)`.
- **`Config.role_llm_model_map`** + **`Config.role_llm_registry`** property:
  Role-specific LLM routing. Per-role model override via
  `Config(role_llm_model_map={"extract": "claude-opus-4-7",
  "translate": "ollama/llama3"})`.
- **CLI `--role-model` flag**: `bp process <url> --role-model
  extract=claude-opus-4-7,translate=ollama/llama3` (per-role CLI override).
- **MCP `_handle_process`**: Now reads `role_llm_model_map` from
  `ConfigManager` and applies to Pipeline.

### Added (Session 31 M2: Source Aggregator Refactor)

- **`_FETCHERS` registry**: `core/source_aggregator.py` refactored from
  5 hardcoded `if _want(...)` blocks to a `_FETCHERS` dict loop
  (mirrors `deliver/_CHANNELS` pattern). New sources can be added via
  `register_source(name, fetcher)` without touching `fetch_all_sources`.
- **`register_source()` + `list_sources()`**: Public API for plugin
  authors to extend source registry (with caveats — see v2.2.0 S2 notes).
- **MCP `_handle_digest`**: Now uses `fetch_all_sources()` consistently.

### Added (v2.2.0 Commit 1: RolePromptRegistry)

- **`builderpulse.remix.prompt_registry`**: New module for role × variant
  prompt template lookup. `step_summarize` now loads prompt template
  keyed by `ctx.source.source_type` (e.g. `summarize-podcast.md`),
  with custom override + builtin fallback + `<role>-default.md` chain.
- Previously: 6 prompt templates existed in `prompts/*.md` but were
  **never called** by `step_summarize` (system="" empty).
  Now: templates wired through Pipeline with graceful degradation
  (missing template → empty system preserves v2.1.0 behavior).

### Changed

- **`AnthropicProvider`**: `complete()` already accepted `system=""`;
  `step_summarize` now actually passes populated system prompt.
- **`Config` default**: `role_llm_model_map={}` defaults; existing
  configs continue to work (`Config()` without role map → role registry
  returns DEFAULT_ROLE_SPECS with `model="auto"`).
- **Version bump**: `pyproject.toml` + `__version__` + `docker-compose.yml`
  aligned to **2.2.0** (R1b B-9 fix).

### Fixed

- **P0-A (R1a)**: `docker-compose.yml` line 15 hardcoded Windows path
  → env var `${HOST_BUILDERPULSE_DIR:-${HOME}/.builderpulse}` for
  cross-platform deploy (Linux/macOS/Windows).
- **P0-B (R1a)**: `RoleLLMRegistry.register_all` polluted global
  `DEFAULT_ROLE_SPECS` via alias mutation. Fixed by `copy.deepcopy`
  in `__init__`. REPL verified: `register_all({"extract": "X"})` no
  longer mutates module state.
- **R1b B-2/B-3/B-4**: 3 同根因 deepcopy 疏漏 — `register()` /
  `__init__(specs=...)` / `get_spec` fallback 全部加 `copy.deepcopy`。
  REPL 实证 8 mutation patterns 全 pass。
- **R1b A-1 (P3)**: `register_source` 错误信息从 "already registered"
  (误导) 改为 "conflicts with built-in source name"。加 warning log
  提醒 plugin author 需手动同步 `_VALID_SOURCES` (P3, 治本推迟到
  v2.3.0 plugin entry_points 重构)。

### Notes (Residual Risks, per H44 R3 self-disclosure)

- **P0-C (test coverage gap)**: Session 31 added 22 new Public API
  elements (11 in `roles.py` + 11 in `source_aggregator.py`) with
  **0 direct unit tests** — only indirect coverage via CLI/MCP/pipeline
  integration tests. **Decision**: S31 owner (this commit) deferred to
  backlog; pytest suite still 609+4 skip pass.
- **9 P1 + 9 P2 items** flagged by R1a V1/V2/V3: see
  `.builderpulse/dev/reviews/s31-lightrag-roles/` for full audit
  (docker aliyun mirror, README stale test count, anthropic SDK upper
  bound, CLI invalid-role warning, etc). Backlog for v2.2.x / v2.3.0.

## [2.2.0] - 2026-06-17 (S1: i18n + Docker)

### Added

- **i18n 双语 README**: split into `README.md` (English) + `README.zh-CN.md`
  (Chinese, preserved). 15 H2 sections correspond 1:1. Bilingual drift test
  prevents translation drift.
- **Docker 化**: multi-stage `Dockerfile` (python:3.12-slim, tini PID 1,
  ffmpeg, ~600MB image) + `docker-compose.yml` (single service, stdio MCP,
  no exposed port) + `.dockerignore`. `docker compose up` one-command
  deploy.
- **Error codes**: `BP_I18N_DRIFT` (BPI18N001) + `BP_DOCKER_BUILD_FAIL`
  (BPDOCKER001).

### Notes

- S2 (Plugin 扩展 4 改动) + S3 (Test + Release) 后续 sub-sessions 追加
- v2.2.0 minor bump per user decision (实际改动量是 major refactor, 但
  shim 保证 no breaking changes)

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
