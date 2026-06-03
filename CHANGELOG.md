# Changelog

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
