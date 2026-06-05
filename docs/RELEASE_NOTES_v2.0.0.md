# BuilderPulse v2.0.0

> **One command replaces 30 minutes of morning browsing.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![Tests: 449 passing](https://img.shields.io/badge/tests-449%20passing-brightgreen.svg)]()

---

## The 30-Second Version

```bash
pip install builderpulse
bp digest --lang zh --deliver telegram
```

You get a daily digest of what AI builders are saying — across YouTube, Bilibili, X/Twitter, podcasts, and blogs — delivered to wherever you read.

**Before:** 30+ minutes of opening tabs, copy-pasting links, summarizing in your head.
**After:** 30 seconds. One command. Delivered.

---

## What's New in v2.0.0

v2 turns BuilderPulse from "two separate scripts" into **one composable pipeline** you can extend.

### 🔌 Plugin System
Drop a Python file in your project. It shows up in `bp` automatically.
- Entry-point discovery via `pyproject.toml`
- Runtime Protocol validation (catches broken plugins before they crash your run)
- **Fault-tolerant lazy loading** — one bad plugin never breaks the others

### 🚀 Batch Manager
Resumable batch jobs for transcribing an entire creator's backlog.
- **SQLite WAL cache** — restart mid-batch without re-processing
- **Token-bucket rate limiter** — won't get you banned by upstream APIs
- **Disk-space guard** — pauses gracefully when you're running out of space
- **Concurrency semaphore** — no fork-bombing your machine

### 🔭 Observability
OpenTelemetry integration. Tracing, metrics, async context.
- Zero-config when OTel is installed
- **No-op stubs when it isn't** — observability is opt-in, never blocking

### 🤖 MCP Server
Full JSON-RPC 2.0 server over stdio. **6 tools** for AI agents.
- `bp_transcribe`, `bp_digest`, `bp_process`, `bp_fetch_feed`, `bp_list_sources`, `bp_config`
- Works with Claude Code, Cursor, Continue, any MCP client
- Content-Length capped at 10 MB, sensitive-key access blocked

### 🔐 Reliability
- 15 typed error codes (no more `Exception: Something went wrong`)
- Retry with exponential backoff (sync + async), transient-only
- ConfigManager with hot-reload and thread-safe singleton
- **Log sanitization** — automatic redaction of API keys in logs

### 📡 New Sources
- **YouTube channels** via RSS
- **Bilibili users** with WBI signing
- **Blog date filtering**

---

## Try It

```bash
# Quickest start
pip install builderpulse
bp digest --lang zh --deliver telegram

# Or: transcribe one video
bp transcribe "https://www.bilibili.com/video/BV1xxxx"

# Or: as an MCP tool in Claude Code / Cursor
bp serve
```

**Optional extras** (pick what you need):
```bash
pip install builderpulse[faster-whisper]    # CPU-friendly transcription
pip install builderpulse[browser]           # Bilibili/Douyin browser mode
pip install builderpulse[sources]           # Twitter / blog / podcast
pip install builderpulse[llm]               # OpenAI / Anthropic / Ollama
```

---

## By the Numbers

| Metric | v1.0.0 | v2.0.0 |
|:-------|:------:|:------:|
| Tests | 126 | **449** |
| Sources | 4 | **6** |
| MCP tools | 8 (3 placeholders) | **6 (all real)** |
| Delivery channels | 6 | 8 |
| Python | 3.9+ | 3.9+ |

---

## Known Limitations

- **X/Twitter API v2** requires paid tier ($100/mo). Nitter RSS fallback provided.
- **Faster-whisper tests** skip without env+deps (documented in test config).
- Some CLI flags in older versions have been renamed — see [MIGRATION.md](MIGRATION.md).

---

## What's Next

We're working on v2.1 with **multi-user authentication** and **scheduled digest delivery** (cron-like). If you have feature requests or want to contribute, the issue tracker is open.

---

## License

MIT — see [LICENSE](../LICENSE).
