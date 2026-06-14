# BuilderPulse

> Stop manually checking 10+ sites for AI builder updates. One command, everything delivered.

**Before:**
```
Morning routine (30+ minutes):
1. Open YouTube → check 5 channels → copy links
2. Open Bilibili → check 3 UP主 → copy links
3. Open X/Twitter → scroll through timeline
4. Open podcast app → check new episodes
5. Open 3 blog RSS feeds → read headlines
6. Manually summarize interesting content
7. Send to yourself on Telegram
```

**After:**
```bash
bp digest --lang zh --deliver telegram
# Done in 30 seconds. 8 tools, 0 manual work.
```

---

## What it does

| Capability | How |
|:-----------|:----|
| **Transcribe** any video to text | YouTube, Bilibili, Douyin, 1000+ sites via yt-dlp |
| **Aggregate** AI builder content | X/Twitter, podcasts, blogs, Bilibili, YouTube |
| **Summarize** with LLM | OpenAI, Anthropic, Ollama — auto-detects |
| **Deliver** to your channels | Telegram, Lark, DingTalk, Discord, Email, WeChat |
| **MCP Server** | Works with Claude Code, Cursor, Continue, any MCP agent |
| **Batch processing** | Resumable batch with SQLite cache, rate limiting, disk guard |
| **Observability** | OpenTelemetry integration for tracing and metrics |
| **Plugin system** | Extensible via Python entry_points |

## Quick Start

```bash
# Install
pip install builderpulse

# Transcribe a video
bp transcribe "https://www.bilibili.com/video/BV1xxx"

# Generate a digest (all sources, Chinese output, send to Telegram)
bp digest --lang zh --deliver telegram

# Batch transcribe a creator
bp batch "https://space.bilibili.com/123456" --limit 20 --summarize

# Use as MCP tool in Claude Code / Cursor
bp serve
```

---

## How to Use BuilderPulse

BuilderPulse has **4 ways** to use it, each suited to a different situation. Pick the one that fits.

### 1. 💻 CLI — for ad-hoc commands and scheduled jobs

**Use this when:** you want a quick command, a cron job, or a one-off task. No setup beyond `pip install`.

#### Daily morning digest (the killer use case)

```bash
bp digest --lang zh --deliver telegram
# → fetches from all sources, summarizes with your LLM, sends to Telegram
# Takes ~30 seconds. Done.
```

Schedule it with `cron` / `Task Scheduler` to fire at 8am daily. See [docs/scheduling.md](docs/scheduling.md) for examples.

#### Transcribe a single video you just found

```bash
bp transcribe "https://www.bilibili.com/video/BV1xxxx" --engine faster-whisper
# → downloads, transcribes (if needed), saves markdown to ./output/
```

#### Catch up on a creator's backlog (resumable)

```bash
bp batch "https://space.bilibili.com/123456" --limit 20 --summarize
# → processes 20 videos. Kill it (Ctrl+C) and restart — picks up where it stopped.
# SQLite cache means you never re-process the same URL.
```

#### Inspect or change config

```bash
bp config show                    # see all settings (secrets masked)
bp config init                    # write a starter config.json
```

---

### 2. 🤖 MCP Server — for AI agents (Claude Code, Cursor, etc.)

**Use this when:** you want your AI agent to do the fetching / transcribing / summarizing for you, conversationally.

#### Setup in Claude Code (`~/.claude.json` or `.mcp.json`)

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "bp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Code. You'll see 6 new tools: `bp_transcribe`, `bp_digest`, `bp_process`, `bp_fetch_feed`, `bp_list_sources`, `bp_config`.

#### What it looks like in conversation

```
You:    "Give me yesterday's AI builder digest, in Chinese, send to my Telegram"
Agent:  [calls bp_digest] → ✓ delivered
```

#### Setup in Cursor / Continue / Windsurf

Same JSON config. The `bp serve` subprocess speaks JSON-RPC 2.0 over stdio, which all MCP clients understand.

---

### 3. 🐍 Python API — for embedding in your own code

**Use this when:** you're building a custom tool, dashboard, or automation that needs the pieces of BuilderPulse without the CLI/MCP layer.

```python
from builderpulse.sources.youtube import YouTubeSource
from builderpulse.remix.summarizer import Summarizer
from builderpulse.deliver import get_channel

# Fetch from a source
src = YouTubeSource()
items = src.fetch(limit=10, days=7)

# Summarize
summarizer = Summarizer(llm="claude")  # or "openai", "ollama"
for item in items:
    item.summary = summarizer.summarize(item.content)

# Deliver
ch = get_channel("telegram")
ch.send(format_digest(items), title="My Daily Digest")
```

Each piece (`sources/`, `remix/`, `deliver/`) is independently importable. See [docs/api.md](docs/api.md) for the full surface.

---

### 4. 🔌 Plugin System — to add your own source / channel

**Use this when:** the 6 built-in sources or 8 built-in channels don't cover what you need.

Drop a Python file with an entry-point in your `pyproject.toml`:

```toml
[project.entry-points."builderpulse.sources"]
my_custom_source = "my_pkg.source:MySource"
```

Your class just needs to satisfy a `Protocol` (a `fetch` method for sources, `deliver` method for channels). It shows up in `bp fetch` / `bp digest` / `bp serve` automatically. See [docs/plugins.md](docs/plugins.md) for the full contract.

---

### 5. ✨ Use cases from the author

These are the three ways I actually use BuilderPulse day-to-day. They cover roughly 95% of my usage.

#### 🌅 Daily morning digest (the daily driver)

Every weekday at 8:05am, Task Scheduler fires `bp digest` on my home Windows box. The result lands in my Telegram while I'm having coffee. I read it on the train.

```cmd
schtasks /create /tn "BuilderPulse Morning" /tr "bp digest --lang zh --sources podcast,youtube,bilibili,blog --deliver telegram" /sc daily /st 08:05
```

Takes ~25 seconds end-to-end. If something catches my eye, I open the source link directly from the Telegram message.

#### 🤖 Inside Claude Code (when working)

I have `bp serve` running as an MCP tool in Claude Code. When I'm coding and want to know "what did [builder] ship this week?" I just ask:

```
> fetch this week's bilibili videos from the creator I'm tracking and summarize the top one
```

Claude Code calls `bp_fetch_feed` → `bp_digest` → returns a one-paragraph summary inline. No context switch, no copy-paste.

```json
// ~/.claude.json
{
  "mcpServers": {
    "builderpulse": { "command": "bp", "args": ["serve"] }
  }
}
```

#### 📚 Saturday backlog catchup (resumable batch)

Saturday morning, second coffee. I run `bp batch` on a creator I'm behind on:

```bash
bp batch "https://space.bilibili.com/123456" --limit 30 --summarize --engine faster-whisper
```

It processes 30 videos. If my Saturday plans interrupt, I `Ctrl+C`. Next Saturday, I re-run — it picks up at video 14 from the SQLite cache, doesn't re-download. `--engine faster-whisper` means no GPU needed, runs fine on CPU.

---

**What about you?** Open an issue or PR to share your use case — the best documentation comes from real workflows.

---

## Choosing the Right Method

| Situation | Use |
|:----------|:----|
| "I just want today's digest in my Telegram" | **CLI** (`bp digest`) |
| "I want it every morning at 8am automatically" | **CLI** + cron / Task Scheduler |
| "My AI agent should do this for me" | **MCP** (Claude Code / Cursor) |
| "I'm building a custom tool on top" | **Python API** |
| "I need a new source / channel" | **Plugin** |
| "I'm catching up on 100 videos" | **CLI** (`bp batch`, resumable) |

---

## How a Typical Pipeline Runs

```
[Source] → [Downloader] → [Transcriber] → [Summarizer] → [Channel]
   ↓            ↓              ↓                ↓             ↓
 YouTube      yt-dlp       faster-whisper    Claude       Telegram
 Bilibili     API+playwright  WhisperX        GPT-4        Email
 Podcasts     RSS+asr       OpenAI Whisper    Ollama       Discord
 Blogs        html scrape
 Twitter      API v2 / Nitter
```

Each stage is independent. If a stage fails, the error is captured with a typed code and the pipeline continues. See [docs/error-codes.md](docs/error-codes.md).

## Installation

```bash
pip install builderpulse                    # Core
pip install builderpulse[whisper]           # + OpenAI Whisper
pip install builderpulse[faster-whisper]    # + faster-whisper (recommended, CPU)
pip install builderpulse[whisperx]          # + WhisperX (best quality, needs GPU)
pip install builderpulse[browser]           # + Playwright for Bilibili/Douyin browser mode
pip install builderpulse[sources]           # + feedparser + tweepy + BeautifulSoup
pip install builderpulse[llm]               # + OpenAI + Anthropic + Ollama SDKs
pip install builderpulse[secrets]           # + keyring for secure credential storage
```

## Configuration

BuilderPulse reads a JSON config file. By default it looks at `~/.builderpulse/config.json`; you can override with the `BUILDERPULSE_CONFIG_PATH` environment variable (12-factor app convention).

```bash
# 1. Copy the example to your home directory
mkdir -p ~/.builderpulse
cp config.example.json ~/.builderpulse/config.json

# 2. Edit it with your own feeds, accounts, and channel credentials
$EDITOR ~/.builderpulse/config.json
```

### What's in `config.example.json`

- **`enabled_sources`** / **`enabled_channels`** — which built-in plugins to use
- **`sources.{podcast,twitter,blog,bilibili,youtube}`** — per-source config
  - `podcast.feeds`: list of RSS feed URLs
  - `twitter.accounts`: list of X/Twitter account handles (requires `X_BEARER_TOKEN` env var)
  - `blog.urls`: list of blog URLs to scrape
  - `bilibili.users`: list of Bilibili user IDs (numeric)
  - `youtube.channels`: list of YouTube channel IDs (`UC...`)
- **Empty lists = "skip this source"** — your cron still runs, the source is just not fetched

### Optional environment variables

| Variable | Purpose | Required? |
|:---------|:--------|:----------|
| `X_BEARER_TOKEN` | X/Twitter API v2 bearer token. Without it, `twitter.accounts` is silently skipped | No (only for Twitter) |
| `BUILDERPULSE_CONFIG_PATH` | Override default config location (`~/.builderpulse/config.json`) | No |
| `BUILDERPULSE_TELEGRAM_BOT_TOKEN`, `BUILDERPULSE_TELEGRAM_CHAT_ID`, etc. | Per-channel credentials (overrides JSON file values) | No (only if you use those channels) |

### Privacy

This repo's `config.example.json` ships with **empty lists only** — your personal feeds and tokens are not (and should never be) committed. Use environment variables or your local `~/.builderpulse/config.json` (gitignored by default) for credentials.

## Supported Sources

| Source | Engine | API Key Required |
|:-------|:-------|:-----------------|
| YouTube / 1000+ sites | yt-dlp | No |
| Bilibili | API + WBI signing | No (SESSDATA optional) |
| Douyin | Playwright | No |
| X/Twitter | API v2 / Nitter RSS | Optional ($100/mo for API) |
| Podcasts | RSS + transcript | No |
| Blogs | HTML scraping | No |

## Agent Integration

BuilderPulse works with any MCP-compatible AI agent.

### Claude Code

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "bp",
      "args": ["serve"]
    }
  }
}
```

Or use the skill: `/builderpulse`

### Cursor

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "bp",
      "args": ["serve"]
    }
  }
}
```

### Continue (VS Code)

```json
{
  "mcpServers": [{
    "name": "builderpulse",
    "command": "bp",
    "args": ["serve"]
  }]
}
```

### Windsurf / Cline / Zed

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "builderpulse-mcp"
    }
  }
}
```

## MCP Tools

The MCP server exposes **6 tools** over JSON-RPC 2.0:

| Tool | Description |
|:-----|:------------|
| `bp_transcribe` | Transcribe a video/audio URL to text |
| `bp_digest` | Generate a multi-source AI builder digest |
| `bp_process` | End-to-end pipeline (download → transcribe → summarize → deliver) |
| `bp_fetch_feed` | Fetch raw content from one source (podcast / blog / twitter / bilibili / youtube) |
| `bp_list_sources` | List all configured content sources and delivery channels |
| `bp_config` | View configuration (secrets masked; sensitive keys blocked) |

See [How to Use → MCP Server](#2-🤖-mcp-server--for-ai-agents-claude-code-cursor-etc) above for setup.

## CLI Commands

```bash
bp transcribe <url>              # Single video transcription
bp batch <user_url> --limit 20   # Batch transcribe creator (resumable)
bp digest --sources podcast,blog # Generate digest
bp fetch bilibili --user <mid>   # Fetch raw content
bp process <url> --summarize     # End-to-end pipeline
bp clean                         # Clean old output files
bp config show                   # Show configuration (secrets masked)
bp config init                   # Write a starter config.json
bp serve                         # Start MCP server
```

## Architecture

```
builderpulse/
├── src/builderpulse/
│   ├── core/          # Config, State (SQLite), Pipeline, models, error codes
│   ├── engines/       # Downloaders (yt-dlp, bilibili, douyin) + Transcribers
│   ├── sources/       # Content aggregation (podcast, blog, twitter, bilibili, youtube)
│   ├── remix/         # LLM summarization + translation
│   ├── deliver/       # 8 delivery channels
│   ├── batch/         # Batch processing (cache, disk guard, rate limiter)
│   ├── plugins/       # Plugin registry (entry_points based)
│   ├── infra/         # Logger, security, i18n, observability, performance
│   ├── cli.py         # CLI entry point
│   └── mcp_server.py  # MCP Server (JSON-RPC over stdio)
├── tests/             # 449 tests
├── prompts/           # LLM prompt templates
├── docs/              # Architecture, plugin dev guide, migration guide
└── .claude-plugin/    # Claude Code plugin manifest
```

### Key Design Patterns

| Pattern | Where | Purpose |
|:--------|:------|:--------|
| **Plugin Registry** | `plugins/` | Extensible via `importlib.metadata.entry_points()` |
| **ConfigManager** | `core/config_manager.py` | Thread-safe singleton with hot-reload |
| **Retry + Fallback** | `batch/retry.py` | Exponential backoff with attempt history |
| **Error Codes** | `core/error_codes.py` | Programmatic error identification |
| **Agent Output** | `infra/agent_output.py` | Versioned JSON schema for MCP clients |
| **Observability** | `infra/observability.py` | OpenTelemetry spans and metrics |
| **SQLite WAL** | `core/state.py`, `batch/cache.py` | Concurrent read/write with crash recovery |

## Stats

- **63 source files** / 6,309 lines of Python (plus 4,695 lines of tests)
- **449 tests** passing
- **6 MCP tools** for AI agent integration (no placeholders — all functional)
- **8 delivery channels** (Telegram, Lark, DingTalk, Discord, Email, WeChat, WeCom, stderr)
- **6 content sources** (YouTube, Bilibili, X/Twitter, Podcasts, Blogs, Douyin)
- **3 transcription engines** (Whisper, WhisperX, faster-whisper)
- **Zero Node.js dependency** — pure Python
- **MIT licensed**

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Plugin Development Guide](docs/plugins.md)
- [Error Code Reference](docs/error-codes.md)
- [v1 → v2 Migration Guide](docs/migration-v2.md)

## License

MIT
