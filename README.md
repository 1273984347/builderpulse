# BuilderPulse

> Track what AI builders are saying — transcripts, digests, and insights delivered to you.

**v1.0.0**

## What it does

- **Transcribe** any video/audio to text (B站/抖音/YouTube/1000+ sites)
- **Aggregate** AI builder content (X/Twitter, Podcasts, Blogs, Bilibili)
- **Summarize** with LLM into structured digests
- **Deliver** to Telegram, Email, 飞书, 钉钉, Discord, and more
- **MCP Server** — call from Claude Code, Cursor, or any AI agent

## Quick Start

```bash
pip install builderpulse

# Transcribe a video
bp transcribe "https://www.youtube.com/watch?v=..."

# Generate a digest
bp digest --lang zh --deliver telegram

# Use as MCP tool (Claude Code)
bp serve
```

## Installation

```bash
pip install builderpulse                    # Core only
pip install builderpulse[whisper]           # + OpenAI Whisper
pip install builderpulse[faster-whisper]    # + faster-whisper (recommended for CPU)
pip install builderpulse[whisperx]          # + WhisperX (best quality, needs GPU)
pip install builderpulse[browser]           # + Playwright for Bilibili/Douyin browser mode
pip install builderpulse[sources]           # + feedparser + tweepy + BeautifulSoup
pip install builderpulse[llm]               # + OpenAI + Anthropic + Ollama SDKs
pip install builderpulse[secrets]           # + keyring for secure credential storage
```

## Supported Sources

| Source | Engine | API Key Required |
|--------|--------|-----------------|
| YouTube / 1000+ sites | yt-dlp | No |
| Bilibili | API + WBI signing | No (SESSDATA optional) |
| Douyin | Playwright | No |
| X/Twitter | API v2 / Nitter RSS | Optional ($100/mo for API) |
| Podcasts | RSS + transcript | No |
| Blogs | HTML scraping | No |

## Agent Integration

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

## MCP Tools

| Tool | Description |
|------|-------------|
| `bp_transcribe` | Transcribe video/audio URL to text |
| `bp_batch_transcribe` | Batch transcribe creator's videos |
| `bp_digest` | Generate AI builder digest |
| `bp_process` | End-to-end pipeline |
| `bp_fetch_feed` | Fetch raw content from source |
| `bp_list_sources` | List configured sources |
| `bp_config` | View/modify config |
| `bp_reload_config` | Hot-reload config |

## License

MIT
