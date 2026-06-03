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
| **Deliver** to your channels | Telegram, 飞书, 钉钉, Discord, Email, WeChat |
| **MCP Server** | Works with Claude Code, Cursor, Continue, any MCP agent |

## Quick Start

```bash
# Install
pip install builderpulse

# Transcribe a video
bp transcribe "https://www.youtube.com/watch?v=..."

# Generate a digest (all sources, Chinese output, send to Telegram)
bp digest --lang zh --deliver telegram

# Use as MCP tool in Claude Code / Cursor
bp serve
```

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

| Tool | Description |
|:-----|:------------|
| `bp_transcribe` | Transcribe video/audio URL to text |
| `bp_batch_transcribe` | Batch transcribe creator's videos |
| `bp_digest` | Generate AI builder digest |
| `bp_process` | End-to-end pipeline |
| `bp_fetch_feed` | Fetch raw content from source |
| `bp_list_sources` | List configured sources |
| `bp_config` | View/modify config |
| `bp_reload_config` | Hot-reload config |

## CLI Commands

```bash
bp transcribe <url>              # Single video transcription
bp batch <user_url> --limit 20   # Batch transcribe creator
bp digest --sources podcast,blog # Generate digest
bp fetch bilibili --user <mid>   # Fetch raw content
bp process <url> --summarize     # End-to-end pipeline
bp clean                         # Clean old output files
bp config show                   # Show configuration
bp serve                         # Start MCP server
```

## Project Structure

```
builderpulse/
├── src/builderpulse/
│   ├── core/          # State, models, config, pipeline
│   ├── engines/       # Downloaders (yt-dlp, bilibili, douyin) + Transcribers
│   ├── sources/       # Content aggregation (podcast, blog, twitter, bilibili, youtube)
│   ├── remix/         # LLM summarization + translation
│   ├── deliver/       # 8 delivery channels
│   ├── infra/         # Logger, secrets, i18n, security
│   ├── cli.py         # CLI entry point
│   └── mcp_server.py  # MCP Server (JSON-RPC over stdio)
├── tests/             # 126 tests
├── prompts/           # LLM prompt templates
└── .claude-plugin/    # Claude Code plugin manifest
```

## Stats

- **81 files** / 6,500+ lines of Python
- **126 tests** passing
- **8 MCP tools** for AI agent integration
- **8 delivery channels** (Telegram, 飞书, 钉钉, Discord, Email, WeChat, 企业微信, stderr)
- **5 content sources** (X/Twitter, Podcasts, Blogs, Bilibili, YouTube)
- **3 transcription engines** (Whisper, WhisperX, faster-whisper)
- **Zero Node.js dependency** — pure Python
