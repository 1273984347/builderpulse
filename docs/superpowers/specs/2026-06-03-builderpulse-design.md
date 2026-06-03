# BuilderPulse — Design Spec

> Track what AI builders are saying — transcripts, digests, and insights delivered to you.

**Date:** 2026-06-03
**Status:** Approved (v2 — post-review fixes)
**Sources:** video2text (D:/1/video2text/) + follow-builders (~/.claude/skills/follow-builders/)

---

## 1. Project Overview

BuilderPulse is an open-source tool that combines video transcription with AI content aggregation. It merges two existing projects:

- **video2text** — Python offline video transcription (Whisper/WhisperX/faster-whisper, yt-dlp, Playwright)
- **follow-builders** — Node.js AI builder content aggregation (X/Twitter, Podcasts, Blogs, Bilibili) with LLM summarization and multi-channel delivery

### Core Value Proposition

```
Raw Content → Download → Transcribe → Summarize → Deliver
   (URL)      (yt-dlp)    (Whisper)     (LLM)     (Telegram/Email)
```

No API keys needed for most content fetching. Keys only needed for:
- **X/Twitter** — Premium source, requires paid API ($100/month Basic tier)
- **Delivery** — Telegram Bot Token / Email API Key
- **Bilibili CC subtitles** — Optional SESSDATA cookie

All other sources (Podcasts, Blogs, YouTube) work without any keys.

---

## 2. Architecture

### Two-Layer Design (Node.js fully removed)

```
┌──────────────────────────────────────────────────────────────┐
│                        BuilderPulse                          │
│                                                              │
│  ┌─── Access Layer ────────────────────────────────────────┐ │
│  │  Claude Code / Cursor / Copilot ──→ MCP Server          │ │
│  │  Human users ──────────────────────→ CLI (click)        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─── Core Layer (Python) ─────────────────────────────────┐ │
│  │  engines/      — download + transcribe (from video2text)│ │
│  │  sources/      — content aggregation (rewritten from JS)│ │
│  │  remix/        — LLM summarization + translation        │ │
│  │  deliver/      — Telegram / Email(SMTP+Resend) / stderr │ │
│  │  infra/        — i18n / security / config / state / log │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Node.js 完全移除**：video2text 已有 `playwright-python`，follow-builders 的 JS 功能全部用 Python 库替代。无双运行时依赖。

### Communication Protocol

- **CLI → Core**: Direct Python function calls
- **MCP Server → Core**: Direct Python function calls (same core)

### Logging Policy (MCP stdio 安全)

**铁律**：Core 层禁止直接 `print()`。所有输出必须通过 `infra/logger.py`。

```
MCP 模式 (bp serve):
  ├─ 正常输出 → MCP JSON-RPC stdout（由 MCP SDK 管理）
  ├─ 进度/日志 → stderr（logger → sys.stderr）
  └─ delivery/stdout → 自动降级为 stderr

CLI 模式 (bp transcribe / bp digest):
  ├─ 正常输出 → stdout（click.echo）
  ├─ 进度/日志 → stderr（logger → sys.stderr）
  └─ delivery/stdout → stdout（正常行为）
```

`infra/logger.py` 必须：
- 检测运行模式（MCP vs CLI）通过环境变量 `BUILDERPULSE_MODE=mcp|cli`
- MCP 模式下所有 handler 指向 stderr
- CLI 模式下 progress bar 用 stderr，结果用 stdout

---

## 3. Directory Structure

```
builderpulse/
├── src/builderpulse/                  # Python package
│   ├── __init__.py                    # v1.0.0
│   ├── cli.py                         # CLI entry point (click)
│   ├── mcp_server.py                  # MCP Server entry point (mcp SDK)
│   │
│   ├── core/                          # Core engine
│   │   ├── pipeline.py                # From video2text + feed mode extension
│   │   ├── models.py                  # SourceRef / DownloadResult / TranscriptResult / FeedItem
│   │   ├── config.py                  # Unified config (Settings + BatchConfig merged)
│   │   ├── state.py                   # Feed dedup state (SQLite, thread-safe)
│   │   └── cache.py                   # Batch cache (filesystem + metadata JSON)
│   │
│   ├── engines/                       # Download + transcribe (from video2text)
│   │   ├── downloaders/
│   │   │   ├── base.py
│   │   │   ├── yt_dlp.py
│   │   │   ├── bilibili.py            # Merged: bilibili.js WBI signing
│   │   │   └── douyin.py              # Merged: bilibili.js Douyin logic
│   │   └── transcribers/
│   │       ├── base.py
│   │       ├── whisper.py
│   │       ├── whisperx.py
│   │       └── faster_whisper.py
│   │
│   ├── sources/                       # Content aggregation (rewritten from follow-builders JS)
│   │   ├── twitter.py                 # tweepy (PREMIUM: requires $100/mo X API)
│   │   ├── podcast.py                 # feedparser replaces RSS regex
│   │   ├── blog.py                    # httpx + BS4 replaces HTML scraping
│   │   ├── bilibili.py                # Bilibili API + WBI
│   │   └── youtube.py                 # YouTube RSS + transcript
│   │
│   ├── remix/                         # LLM summarization (from follow-builders prompts)
│   │   ├── prompts.py                 # Load/manage prompt templates (custom overrides builtin)
│   │   ├── summarizer.py              # LLM adapter pattern (OpenAI / Anthropic / Ollama)
│   │   └── translator.py              # Translation (zh↔en / bilingual)
│   │
│   ├── deliver/                       # Delivery (rewritten from deliver.js)
│   │   ├── base.py                  # DeliveryChannel ABC (统一接口)
│   │   ├── telegram.py
│   │   ├── email_sender.py          # SMTP + Resend dual backend
│   │   ├── stderr_fallback.py       # MCP-safe output (stderr)
│   │   ├── wechat.py                # PushPlus / Server酱 / WxPusher
│   │   ├── lark.py                  # 飞书 Webhook
│   │   ├── dingtalk.py              # 钉钉 Webhook
│   │   ├── wecom.py                 # 企业微信 Webhook
│   │   └── discord.py               # Discord Webhook
│   │
│   └── infra/                         # Infrastructure (from douyin_batch)
│       ├── i18n.py
│       ├── security.py
│       ├── platform_compat.py
│       ├── progress.py
│       ├── logger.py                # MCP-aware: stderr in MCP mode
│       └── secrets.py              # Keyring + file permission 600
│
├── prompts/                           # Prompt templates (from follow-builders/prompts/)
│   ├── digest-intro.md
│   ├── summarize-tweets.md
│   ├── summarize-podcast.md
│   ├── summarize-blogs.md
│   ├── summarize-bilibili.md
│   └── translate.md
│
├── config/                            # Source configs (from follow-builders/config/)
│   ├── default-sources.json
│   ├── cn-sources.json
│   └── config-schema.json
│
├── examples/
│   ├── sample-digest.md
│   └── sample-transcript.md
│
├── tests/
│   ├── test_pipeline.py
│   ├── test_sources.py
│   ├── test_downloaders.py
│   ├── test_transcribers.py
│   ├── test_mcp.py
│   └── test_cli.py
│
├── .github/workflows/
│   ├── test.yml                       # CI (from video2text)
│   └── generate-feed.yml              # Scheduled feed update (from follow-builders)
│
├── pyproject.toml
├── README.md
├── README.zh-CN.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                            # MIT
└── .gitignore
```

---

## 4. Code Integration Strategy

### What to Keep (direct port)

| Module | Source | Action |
|:-------|:-------|:-------|
| `engines/downloaders/*` | video2text/downloaders/ | Port directly, adjust imports |
| `engines/transcribers/*` | video2text/transcribers/ | Port directly |
| `core/pipeline.py` | video2text/pipeline.py | Port + extend for feed mode |
| `core/models.py` | video2text/models.py | Port + add FeedItem |
| `infra/i18n.py` | douyin_batch/i18n.py | Port directly |
| `infra/security.py` | douyin_batch/security.py | Port directly |
| `infra/platform_compat.py` | douyin_batch/platform_compat.py | Port directly |
| `infra/progress.py` | douyin_batch/progress.py | Port directly |
| `infra/logger.py` | douyin_batch/logger.py | Port directly |
| `prompts/*` | follow-builders/prompts/ | Copy directly |
| `config/*` | follow-builders/config/ | Copy directly |

### What to Rewrite (JS → Python)

| New Module | Replaces | Python Library |
|:-----------|:---------|:---------------|
| `sources/twitter.py` | generate-feed.js X section | tweepy |
| `sources/podcast.py` | generate-feed.js RSS section | feedparser |
| `sources/blog.py` | generate-feed.js blog section | httpx + BeautifulSoup |
| `sources/bilibili.py` | bilibili.js Bilibili mode | requests (WBI signing) |
| `sources/youtube.py` | generate-feed.js YouTube section | feedparser + httpx |
| `deliver/base.py` | (new) | ABC interface for all channels |
| `deliver/telegram.py` | deliver.js Telegram | httpx |
| `deliver/email_sender.py` | deliver.js Email | httpx (Resend) + smtplib (SMTP fallback) |
| `deliver/stderr_fallback.py` | deliver.js Stdout | sys.stderr (MCP-safe) |
| `deliver/wechat.py` | (new) | httpx (PushPlus/Server酱/WxPusher) |
| `deliver/lark.py` | (new) | httpx (飞书 Webhook) |
| `deliver/dingtalk.py` | (new) | httpx (钉钉 Webhook) |
| `deliver/wecom.py` | (new) | httpx (企业微信 Webhook) |
| `deliver/discord.py` | (new) | httpx (Discord Webhook) |
| `remix/summarizer.py` | LLM prompt execution | openai / anthropic SDK |
| `remix/translator.py` | translate.md execution | same |
| `cli.py` | video2text __main__ + douyin_batch_v3 | click |
| `mcp_server.py` | (new) | mcp SDK |

### What to Delete (not migrated)

| File | Reason |
|:-----|:-------|
| douyin_batch.py / v2 / v3 | Replaced by cli.py |
| douyin_auto_download.py | Merged into engines/douyin.py |
| douyin_user_scraper.py | Merged into engines/douyin.py |
| get_user_url.py | Merged into engines/douyin.py |
| convert_to_md.py | Internalized into pipeline.py |
| demo.py / demo_v3.py | Replaced by examples/ |
| process_douyin.py | Replaced by CLI |
| bilibili.js | Replaced by sources/bilibili.py + engines/downloaders/bilibili.py |
| generate-feed.js | Replaced by sources/*.py + cli.py |
| prepare-digest.js | Replaced by `bp digest` |
| deliver.js | Replaced by deliver/*.py |

---

## 5. CLI Interface

```bash
# ── Transcribe ──
bp transcribe <url>                     # Single video
bp transcribe <url> --engine whisperx   # Specify engine
bp transcribe <url> --language zh       # Specify language
bp batch <user_url> --limit 20          # Batch transcribe creator

# ── Aggregate + Summarize ──
bp digest                               # Full digest (all sources)
bp digest --sources twitter,podcast     # Specific sources
bp digest --lang zh                     # Chinese output
bp digest --days 3                      # Lookback 3 days
bp digest --deliver telegram            # Single channel
bp digest --deliver telegram,lark       # Multi-channel (comma-separated)
bp digest --skip-failed-sources         # Don't abort if one source fails
bp digest --no-state                    # Force full fetch, ignore dedup state

# ── Fetch Raw ──
bp fetch twitter --limit 10             # ⚠️ Requires X_BEARER_TOKEN (paid)
bp fetch podcast --days 7
bp fetch blog
bp fetch bilibili --user <mid>          # Uses WBI signing (default)
bp fetch bilibili --user <mid> --cookie-file cookies.txt  # Use browser cookies

# ── End-to-End Pipeline ──
bp process <url>                        # Download → Transcribe → Output
bp process <url> --summarize            # + LLM summary
bp process <url> --deliver telegram     # + delivery
bp process <url> --deliver telegram,lark,dingtalk  # Multi-channel
bp process <url> --pipeline "transcribe,summarize,translate,deliver=email"

# ── Maintenance ──
bp clean                                # Delete output files older than 7 days
bp clean --all                          # Delete all output files
bp clean --dry-run                      # Show what would be deleted

# ── Config ──
bp config set language zh
bp config set delivery.telegram <token> # Stored in keyring (not plaintext)
bp config set engine faster-whisper
bp config show                          # Secrets shown as ****
bp config reload                        # Hot-reload config.json without restart
bp config migrate --from ~/.follow-builders/  # Migrate from follow-builders

# ── MCP Server ──
bp serve                                # stdio mode (default for agents)
bp serve --port 3000                    # SSE mode (for web/remote)
```

---

## 6. MCP Server Tools

| Tool | Description | Key Parameters |
|:-----|:------------|:---------------|
| `bp_transcribe` | Transcribe video/audio URL to text | `url`, `engine`, `language`, `output_format` |
| `bp_batch_transcribe` | Batch transcribe creator's videos | `user_url`, `limit`, `language` |
| `bp_digest` | Generate AI builder digest | `sources`, `language`, `days`, `deliver` |
| `bp_process` | End-to-end pipeline: download → transcribe → summarize → deliver | `url`, `pipeline`, `deliver` |
| `bp_fetch_feed` | Fetch raw content from source | `source`, `limit`, `days` |
| `bp_list_sources` | List configured sources | (none) |
| `bp_config` | View/modify config | `action`, `key`, `value` |
| `bp_reload_config` | Hot-reload config.json without restart | (none) |

### MCP Config (for Claude Code / Cursor)

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

---

## 7. Configuration

### File: `~/.builderpulse/config.json`

```json
{
  "language": "zh",
  "engine": "whisper",
  "model": "base",
  "device": "auto",
  "sources": {
    "twitter": { "enabled": false, "accounts": ["karpathy", "ylecun"], "_note": "Premium: requires $100/mo X API" },
    "podcast": { "enabled": true, "feeds": ["latent-space", "no-priors"] },
    "blog": { "enabled": true, "urls": ["anthropic.com/blog"] },
    "bilibili": { "enabled": true, "users": [{"mid": 946974, "name": "3B1B"}] }
  },
  "delivery": {
    "method": "stderr",
    "telegram": { "botToken": "", "chatId": "" },
    "email": { "provider": "smtp", "smtp": { "host": "", "port": 587, "user": "", "password": "" }, "resend": { "apiKey": "" }, "to": "" },
    "wechat": { "type": "pushplus", "token": "", "topic": "" },
    "lark": { "webhook_url": "", "secret": "" },
    "dingtalk": { "webhook_url": "", "secret": "" },
    "wecom": { "webhook_url": "" },
    "discord": { "webhook_url": "" }
  },
  "remix": {
    "model": "claude-sonnet-4-6",
    "customPromptsDir": "~/.builderpulse/prompts/",
    "chunkSize": 30000,
    "chunkOverlap": 2000
  },
  "workspace": "~/.builderpulse/output/",
  "cleanup": {
    "autoTTL": "7d",
    "maxSize": "5GB"
  }
}
```

### Priority

`CLI args > Env vars > ~/.builderpulse/config.json > Built-in defaults`

### Security (Fix #6)

敏感字段存储策略：
1. **首选**：系统 keyring（`keyring` 库，跨平台密钥环）
2. **降级**：`~/.builderpulse/secrets.json`，权限 `600`（仅 owner 可读写）
3. **禁止**：敏感字段不得写入 `config.json`

```python
# infra/secrets.py
def set_secret(key: str, value: str):
    """Store in keyring. Falls back to secrets.json with chmod 600."""
    try:
        import keyring
        keyring.set_password("builderpulse", key, value)
    except Exception:
        _write_secrets_file(key, value)  # chmod 600

def get_secret(key: str) -> str | None:
    """Read from keyring, then secrets.json, then env var."""
```

`bp config show` 显示敏感字段时自动脱敏：`telegram.botToken: ****`。
`bp config set --secret <key>` 隐藏输入（`getpass`）。

### X/Twitter 降级策略 (Fix #4)

```
bp fetch twitter:
  ├─ X_BEARER_TOKEN 存在？→ 正常 API 调用
  ├─ 无 token？→ 尝试 Nitter RSS（公开实例轮换）
  └─ Nitter 也失败？→ 跳过，记录 warning，不中断 digest
```

`bp digest --skip-failed-sources`（默认开启）：单个源失败不阻塞整体摘要。

### Env Vars

| Variable | Purpose | Required |
|:---------|:--------|:---------|
| `X_BEARER_TOKEN` | X/Twitter API (paid) | No (degrades gracefully) |
| `POD2TXT_API_KEY` | Podcast transcript service | No (falls back to RSS description) |
| `BILIBILI_SESSDATA` | Bilibili CC subtitles | No (falls back to Whisper ASR) |
| `TELEGRAM_BOT_TOKEN` | Telegram delivery | Only for Telegram |
| `TELEGRAM_CHAT_ID` | Telegram delivery | Only for Telegram |
| `BUILDERPULSE_CONFIG` | Custom config path | No |

---

## 8. Node.js — 完全移除

**决策**：Node.js 层完全移除，不保留可选层。

**理由**：
- `playwright-python` 与 Node.js Playwright 功能完全等价
- subprocess + stdout JSON 通信是脆弱接口（console.log / deprecation warnings 污染 stdout）
- 双运行时是用户安装的最大障碍
- 所有 follow-builders 的 JS 功能都有 Python 等价实现

**迁移影响**：
- 原 follow-builders 的 GitHub Actions workflow 改用 Python 脚本
- 原 bilibili.js 的浏览器自动化改用 `playwright-python`
- 原 `node bilibili.js --browser` 改用 `bp fetch bilibili --user <mid>`

---

## 9. Package Distribution

### Version Strategy

首次发布使用 `v0.9.0`（beta），明确告知用户 API 和 CLI 接口在 v1.0.0 前可能调整。

### Dependency Strategy (Fix #2 — Whisper 依赖地狱)

三引擎互斥安装，避免 CUDA/CTranslate2 冲突：

```toml
[project]
name = "builderpulse"
version = "0.9.0"
requires-python = ">=3.9"
dependencies = [
    "click>=8.0",
    "httpx>=0.24",
    "yt-dlp>=2024.1.0",
    "feedparser>=6.0",
    "beautifulsoup4>=4.12",
    "mcp>=1.0",
    "pydantic>=2.0",
    "keyring>=24.0",
    "rich>=13.0",              # progress bars, styled output
]

[project.optional-dependencies]
# Transcription engines (pick ONE — they conflict)
whisper = ["openai-whisper>=20231117", "torch>=2.0"]
whisperx = ["whisperx>=3.1.1", "torch>=2.0", "pyannote.audio>=3.0"]
faster-whisper = ["faster-whisper>=0.10"]
# Browser automation (Bilibili + Douyin browser mode)
browser = ["playwright>=1.40"]
# CPU-only variant (no CUDA)
cpu = ["openai-whisper>=20231117", "torch>=2.0 --index-url https://download.pytorch.org/whl/cpu"]
# Dev
dev = ["pytest>=7.4", "pytest-cov>=4.1", "ruff>=0.1"]
```

```bash
pip install builderpulse                    # Core only (no transcription engine)
pip install builderpulse[whisper]           # + OpenAI Whisper
pip install builderpulse[faster-whisper]    # + faster-whisper (recommended for CPU)
pip install builderpulse[whisperx]          # + WhisperX (best quality, needs GPU)
pip install builderpulse[browser]           # + Playwright for Bilibili/Douyin browser mode
pip install builderpulse[cpu]               # + Whisper CPU-only (no CUDA)
```

**不提供 `builderpulse[all]`** — 因为 whisper/whisperx/faster-whisper 互相冲突。
**CI 必须测试** `pip install builderpulse[whisper]` 和 `pip install builderpulse[faster-whisper]` 的真实安装。

### Whisper 引擎运行时检测

```python
# engines/transcribers/__init__.py
def get_transcriber(engine: str = "auto") -> Transcriber:
    if engine == "auto":
        # 尝试顺序: faster-whisper > whisperx > whisper
        for name in ["faster_whisper", "whisperx", "whisper"]:
            try:
                return _load_engine(name)
            except ImportError:
                continue
        raise ImportError(
            "No transcription engine installed. "
            "Run: pip install builderpulse[whisper] or builderpulse[faster-whisper]"
        )
    return _load_engine(engine)
```

---

## 10. GitHub Actions

### CI (test.yml)
- Matrix: Python 3.9-3.12 × Ubuntu/macOS/Windows
- Steps:
  1. Install ffmpeg
  2. `pip install builderpulse[faster-whisper,dev]`（测试真实安装）
  3. `pytest` — Whisper 模型加载必须 mock（`pytest-vcr` 或 monkeypatch），CI 不下载模型
  4. `ruff check` + `ruff format --check`
- Separate job: `pip install builderpulse[whisper]` 安装测试（只测 import，不跑推理）

### Scheduled Feed (generate-feed.yml)
- Cron: daily 6:17am UTC
- Steps: pip install builderpulse, bp fetch all --output feeds/ --format json, commit + push
- Secrets: X_BEARER_TOKEN, POD2TXT_API_KEY
- `--skip-failed-sources` 确保单个源失败不阻塞

---

## 11. State Management (Fix #3)

### Feed State — SQLite

```python
# core/state.py
"""Feed deduplication state. Thread-safe via SQLite WAL mode."""
DB_PATH = "~/.builderpulse/state/feed.db"

# Schema:
# CREATE TABLE seen_items (
#   source TEXT,        -- 'twitter' | 'podcast' | 'blog' | 'bilibili'
#   item_id TEXT,       -- tweet GUID / episode GUID / article URL / BV号
#   content_hash TEXT,  -- 内容指纹（防重复）
#   seen_at TIMESTAMP,
#   PRIMARY KEY (source, item_id)
# );
# CREATE TABLE source_cursors (
#   source TEXT PRIMARY KEY,  -- 'twitter' | 'podcast' | ...
#   source_id TEXT,           -- account/feed URL/user mid
#   last_cursor TEXT,         -- 分页游标或时间戳
#   updated_at TIMESTAMP
# );
# CREATE INDEX idx_seen_at ON seen_items(seen_at);
#
# 自动清理：DELETE WHERE seen_at < datetime('now', '-14 days')
```

**选择 SQLite 而非 JSON 的理由**：
- 进程崩溃不损坏（WAL 模式）
- 并发安全（读写分离）
- 查询高效（索引 + WHERE）
- 自带清理（SQL DELETE）

### Batch Cache — Filesystem

```python
# core/cache.py
"""Batch processing cache. Filesystem-based with metadata JSON."""
CACHE_DIR = "~/.builderpulse/cache/"
# Structure:
#   <user_id>/
#     metadata.json    -- { "videos": [...], "last_scan": "..." }
#     <video_id>.json  -- { "status": "done|pending|failed", "transcript": "..." }
```

**分离理由**：Feed 状态是高频小写入（每次 digest 更新），Batch 缓存是大文件 I/O（转录结果）。访问模式不同，不应合并。

### 文件锁

Feed state 使用 SQLite 内置锁。Batch cache 使用 `portalocker` 文件锁，防止并行 CLI 实例冲突。

### 数据清理

```bash
bp clean              # 删除 output/ 中 >7 天的文件 + 清理过期 cache
bp clean --all        # 删除所有 output/
bp clean --dry-run    # 预览
```

自动清理：`cleanup.autoTTL` 配置项（默认 7d），每次 `bp digest` 后触发。

---

## 11.5 Bilibili WBI 签名维护

B站频繁更换签名算法。设计要求：

```python
# engines/downloaders/bilibili.py
class BilibiliDownloader:
    def _sign_request(self, params: dict) -> dict:
        """WBI signing. Algorithm updated via config hot-reload."""
        mixin_key = self._get_mixin_key()  # 从 B 站 API 动态获取
        # ...
```

- 签名逻辑抽象为独立方法，允许通过配置文件热更新 mixin_key_tab
- 提供 `--no-sign` 模式：使用 SESSDATA cookie 跳过签名（需登录）
- 提供 `bp config update-bilibili-key` 命令手动刷新

---

## 11.6 LLM 摘要分块策略

长内容（2 小时播客 >100k tokens）超出模型上下文。`remix/summarizer.py` 必须实现：

```
Map-Reduce 策略：
  1. 按 chunkSize（默认 30k tokens）分块
  2. 每块独立摘要（并行调用 LLM）
  3. 合并摘要块 → 最终摘要
```

配置项：`remix.chunkSize`、`remix.chunkOverlap`。

---

## 11.7 LLM Provider 适配器

`remix/summarizer.py` 使用适配器模式，统一调用接口：

```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, system: str = "", temperature: float = 0.3) -> str: ...

class OpenAIProvider(LLMProvider): ...      # gpt-4o, gpt-4o-mini
class AnthropicProvider(LLMProvider): ...    # claude-sonnet-4-6
class OllamaProvider(LLMProvider): ...       # ollama/llama3, ollama/qwen2
```

**自动路由**：根据 `remix.model` 前缀选择 provider：
- `claude-*` → AnthropicProvider
- `gpt-*` → OpenAIProvider
- `ollama/*` → OllamaProvider
- 其他 → 报错 + 提示可用模型

**配置**：
```json
"remix": {
    "model": "claude-sonnet-4-6",
    "providers": {
        "openai": { "api_key": "$OPENAI_API_KEY", "base_url": null },
        "anthropic": { "api_key": "$ANTHROPIC_API_KEY" },
        "ollama": { "host": "http://localhost:11434" }
    }
}
```

**CLI 临时切换**：`bp digest --model ollama/llama3`

---

## 11.8 MCP 进度反馈

长时间操作（转录/摘要）通过 MCP `notifications/progress` 推送进度：

```python
async def bp_transcribe(url, ..., progress_token=None):
    if progress_token:
        await server.notify_progress(progress_token, 0.0, "Downloading...")
    # ... download
    if progress_token:
        await server.notify_progress(progress_token, 0.3, "Transcribing...")
    # ... transcribe
    if progress_token:
        await server.notify_progress(progress_token, 1.0, "Done")
    return result
```

CLI 模式使用 `rich.progress` 显示进度条（stderr）。

---

## 11.9 Custom Prompt 覆盖策略

`remix/prompts.py` 加载顺序：

```
1. ~/.builderpulse/prompts/<name>.md  — 用户自定义（完全覆盖同名内置）
2. <package>/prompts/<name>.md         — 内置默认
3. 都不存在 → FileNotFoundError
```

**规则**：自定义模板**完全替代**同名内置模板，不合并。如需扩展，请用不同文件名。

CLI：`bp digest --custom-prompts ~/my-prompts` 临时指定目录。

---

## 11.10 Delivery Channel 扩展

### 统一接口

```python
# deliver/base.py
class DeliveryChannel(ABC):
    @abstractmethod
    def send(self, content: str, title: str = "", content_type: str = "text") -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
```

所有渠道实现同一接口。新增渠道只需添加一个模块 + 配置字段。

### 渠道清单

| 渠道 | 推送方式 | 依赖 | 配置字段 |
|:-----|:---------|:-----|:---------|
| Telegram | Bot API | httpx | `telegram.botToken`, `telegram.chatId` |
| Email | SMTP + Resend | smtplib / httpx | `email.provider`, `email.smtp.*` / `email.resend.*` |
| stderr | 直接输出 | 无 | `method: "stderr"` |
| **微信** | PushPlus / Server酱 / WxPusher | httpx | `wechat.type`, `wechat.token` |
| **飞书** | 自定义机器人 Webhook | httpx | `lark.webhook_url`, `lark.secret` |
| **钉钉** | 自定义机器人 Webhook | httpx | `dingtalk.webhook_url`, `dingtalk.secret` |
| **企业微信** | 群机器人 Webhook | httpx | `wecom.webhook_url` |
| **Discord** | Webhook | httpx | `discord.webhook_url` |

所有渠道零额外依赖（仅 httpx，已是核心依赖）。

### 配置扩展

```json
{
  "delivery": {
    "method": "lark",
    "telegram": { "botToken": "", "chatId": "" },
    "email": { "provider": "smtp", "smtp": { "host": "", "port": 587, "user": "", "password": "" } },
    "wechat": { "type": "pushplus", "token": "", "topic": "" },
    "lark": { "webhook_url": "", "secret": "" },
    "dingtalk": { "webhook_url": "", "secret": "" },
    "wecom": { "webhook_url": "" },
    "discord": { "webhook_url": "" }
  }
}
```

### 多渠道投递

CLI 支持逗号分隔多渠道，按序发送，单个失败不阻塞：

```bash
bp process <url> --deliver telegram,lark,dingtalk
bp digest --deliver wechat,discord
```

### 长消息自动分片

有字符限制的渠道（Discord 2000、钉钉 20000）在 `send()` 内自动按段落分片：

```python
def _chunk_markdown(self, content: str, max_len: int) -> list[str]:
    paragraphs = content.split("\n\n")
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) + 2 > max_len:
            chunks.append(current)
            current = p
        else:
            current += f"\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks
```

### 重试策略

每个渠道 3 次重试，指数退避（1s → 2s → 4s），全部失败记录日志但不阻塞流水线。

---

## 11.11 Migration Path

| Existing User | Migration |
|:--------------|:----------|
| follow-builders | `pip install builderpulse` → `bp config migrate --from ~/.follow-builders/` |
| video2text | `pip install builderpulse` → `video2text` command maps to `bp transcribe` |
| bilibili.js | `bp fetch bilibili --user <mid>` replaces `node bilibili.js --browser` |
| GitHub Actions | Workflow auto-updates, feed URLs unchanged |

---

## 12. Success Criteria

1. `pip install builderpulse[faster-whisper] && bp transcribe <url>` works on fresh machine (with ffmpeg)
2. `bp serve` starts MCP server, Claude Code can call `bp_transcribe` tool — **no stdout pollution**
3. `bp digest --lang zh` generates same quality digest as follow-builders
4. All video2text tests pass after port
5. All follow-builders feed sources work in Python version
6. No Node.js dependency anywhere
7. `pip install builderpulse[whisper]` and `pip install builderpulse[faster-whisper]` both install without conflicts
8. `bp config show` hides all secrets
9. `bp clean --dry-run` shows reclaimable space
10. Feed state survives concurrent CLI + GitHub Actions access (SQLite WAL)
