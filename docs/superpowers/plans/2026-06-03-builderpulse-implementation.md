# BuilderPulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge video2text (Python transcription) + follow-builders (Node.js content aggregation) into a single Python open-source tool with MCP Server support.

**Architecture:** Python core with two access layers (CLI via click, MCP Server via mcp SDK). Content sources (Twitter/Podcast/Blog/Bilibili) rewritten from JS to Python. Transcription engines ported from video2text. Delivery channels unified under one ABC. SQLite state management. No Node.js dependency.

**Tech Stack:** Python 3.9+, click, httpx, yt-dlp, feedparser, BeautifulSoup4, mcp SDK, pydantic, SQLite, rich

**Task Sizes:** ⚡micro / 📦small / 🏗️large (per task below)

**DAG 依赖图:**
```
T1 ✅ ──→ T2 ──→ T3 ──→ T19 (CLI)
T4 ─────→ T5 ──→ T19
T6 ─────→ T19
T7 ─────→ T8,T9,T10 ──→ T12 ──→ T19
T11 ────→ T12
T13,T14,T15,T16 ──→ T19
T17 ────→ T19
T18 ────→ T19
T19 ────→ T20 (MCP)
T21 ────→ T22 ──→ T23
T24 (E2E, 最后)

关键路径: T1→T2→T3→T12→T19→T20→T24
```

---

## Spec Compliance Checkpoint

| Spec Section | 对应 Task | 状态 |
|:---|:---|:---|
| §1 Project Overview | 全局（无需单独 task） | ✅ |
| §2 Architecture | T4 (logger), T19 (CLI), T20 (MCP) | ✅ |
| §3 Directory Structure | 各 task 创建文件时覆盖 | ✅ |
| §4 Code Integration | T7-T10 (engines), T11 (transcribers), T12 (pipeline), T13-T16 (sources), T17 (remix), T18 (deliver) | ✅ |
| §5 CLI Interface | T19 | ✅ |
| §6 MCP Server | T20 | ✅ |
| §7 Configuration | T3 (config), T5 (secrets) | ✅ |
| §8 Node.js Removal | 已确认，无需 task | ✅ |
| §9 Package Distribution | T22 (pyproject.toml 完善) | ✅ |
| §10 GitHub Actions | T23 | ✅ |
| §11 State Management | T1 ✅ | ✅ |
| §11.5 Bilibili WBI | T9 | ✅ |
| §11.6 LLM Chunking | T17 | ✅ |
| §11.7 LLM Provider | T17 | ✅ |
| §11.8 MCP Progress | T20 | ✅ |
| §11.9 Custom Prompts | T17 | ✅ |
| §11.10 Delivery Channels | T18 | ✅ |
| §11.11 Migration | T21 | ✅ |
| §12 Success Criteria | T24 (E2E verification) | ✅ |

---

## Phase 1: Core Foundation

### Task 1: core/state.py — SQLite 状态管理 (📦small) ✅ DONE

**Files:**
- `EXISTS:` `src/builderpulse/core/state.py` — 410 行，State 类 + 幂等键 + 状态机 + 崩溃恢复
- `EXISTS:` `tests/test_state.py` — 290 行，41 个测试全绿

**状态:** 已完成。41/41 passed。

---

### Task 2: core/models.py — 数据模型 (📦small)

**Files:**
- `NEW:` `src/builderpulse/core/models.py` — Pydantic dataclasses
- `NEW:` `tests/test_models.py`

**依赖:** T1

- [ ] **Step 1: Write tests**

```python
# tests/test_models.py
from builderpulse.core.models import SourceRef, DownloadResult, TranscriptResult, FeedItem

def test_source_ref_video():
    ref = SourceRef.from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert ref.source_type == "youtube"
    assert ref.native_id == "dQw4w9WgXcQ"

def test_source_ref_bilibili():
    ref = SourceRef.from_url("https://www.bilibili.com/video/BV1Nd596vEyU")
    assert ref.source_type == "bilibili"
    assert ref.native_id == "BV1Nd596vEyU"

def test_source_ref_douyin():
    ref = SourceRef.from_url("https://v.douyin.com/abc123/")
    assert ref.source_type == "douyin"

def test_source_ref_local_file():
    ref = SourceRef.from_url("/path/to/video.mp4")
    assert ref.source_type == "local"

def test_download_result():
    dr = DownloadResult(path="/tmp/video.mp4", source_type="youtube", native_id="abc", title="Test", duration=120)
    assert dr.path == "/tmp/video.mp4"

def test_transcript_result():
    tr = TranscriptResult(text="Hello world", language="en", engine="whisper", segments=[{"start": 0, "end": 1, "text": "Hello"}])
    assert tr.word_count == 2

def test_feed_item():
    fi = FeedItem(source_type="tweet", source_id="123", url="https://x.com/user/status/123", title="Hello", content="World", author="Test")
    assert fi.idem_key == "tweet:123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_models.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement models.py**

```python
# src/builderpulse/core/models.py
"""Data models for BuilderPulse."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs
from .state import make_idem_key, make_idem_key_from_url

@dataclass
class SourceRef:
    """Reference to a content source (video, tweet, podcast episode, etc.)."""
    source_type: str  # youtube, bilibili, douyin, twitter, podcast, blog, local
    native_id: str    # platform-native ID (BV号, tweet_id, guid, etc.)
    url: str
    title: Optional[str] = None

    @classmethod
    def from_url(cls, url: str) -> SourceRef:
        """Parse URL into SourceRef with auto-detected source type."""
        if url.startswith("/") or url.startswith("./"):
            return cls(source_type="local", native_id=url, url=url)
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if "youtube.com" in host or "youtu.be" in host:
            video_id = _extract_youtube_id(parsed)
            return cls(source_type="youtube", native_id=video_id, url=url)
        elif "bilibili.com" in host:
            bvid = _extract_bvid(parsed.path)
            return cls(source_type="bilibili", native_id=bvid, url=url)
        elif "douyin.com" in host:
            return cls(source_type="douyin", native_id=parsed.path.strip("/"), url=url)
        elif "x.com" in host or "twitter.com" in host:
            parts = parsed.path.split("/")
            tweet_id = parts[-1] if parts else ""
            return cls(source_type="twitter", native_id=tweet_id, url=url)
        else:
            return cls(source_type="web", native_id=make_idem_key_from_url(url), url=url)

    @property
    def idem_key(self) -> str:
        return make_idem_key(self.source_type, self.native_id)

def _extract_youtube_id(parsed) -> str:
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/")
    qs = parse_qs(parsed.query)
    return qs.get("v", [""])[0]

def _extract_bvid(path: str) -> str:
    import re
    m = re.search(r"BV[a-zA-Z0-9]+", path)
    return m.group(0) if m else path

@dataclass
class DownloadResult:
    path: str
    source_type: str
    native_id: str
    title: Optional[str] = None
    duration: Optional[float] = None

@dataclass
class TranscriptResult:
    text: str
    language: str
    engine: str
    segments: list[dict] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

@dataclass
class FeedItem:
    """Aggregated content item from a feed source."""
    source_type: str
    source_id: str
    url: str
    title: str
    content: str
    author: str
    published_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def idem_key(self) -> str:
        return make_idem_key(self.source_type, self.source_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_models.py -v`
Expected: 7/7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/builderpulse/core/models.py tests/test_models.py
git commit -m "feat(core): add data models - SourceRef, DownloadResult, TranscriptResult, FeedItem"
```

---

### Task 3: core/config.py — 统一配置 (📦small)

**Files:**
- `NEW:` `src/builderpulse/core/config.py`
- `NEW:` `tests/test_config.py`

**依赖:** T2

- [ ] **Step 1: Write tests**

```python
# tests/test_config.py
import json, tempfile, os
from pathlib import Path
from builderpulse.core.config import Config

def test_default_config():
    cfg = Config()
    assert cfg.language == "en"
    assert cfg.engine == "auto"

def test_load_from_file(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"language": "zh", "engine": "whisper"}))
    cfg = Config.from_file(cfg_file)
    assert cfg.language == "zh"
    assert cfg.engine == "whisper"

def test_env_override(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"language": "en"}))
    monkeypatch.setenv("BUILDERPULSE_LANGUAGE", "zh")
    cfg = Config.from_file(cfg_file)
    assert cfg.language == "zh"

def test_secret_fields_not_in_dict():
    cfg = Config()
    cfg.telegram_bot_token = "secret123"
    d = cfg.to_dict()
    assert "secret123" not in json.dumps(d)
    assert d["delivery"]["telegram"]["botToken"] == "****"
```

- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement config.py** — Pydantic BaseSettings with env var support, secret masking, file load
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

### Task 4: infra/logger.py — MCP-aware 日志 (📦small)

**Files:**
- `NEW:` `src/builderpulse/infra/__init__.py`
- `NEW:` `src/builderpulse/infra/logger.py`
- `NEW:` `tests/test_logger.py`

**依赖:** 无

- [ ] **Step 1: Write tests** — 验证 MCP 模式输出到 stderr，CLI 模式输出到 stdout
- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement logger.py** — 检测 `BUILDERPULSE_MODE` env var，MCP 模式所有 handler → stderr
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

### Task 5: infra/secrets.py — 密钥管理 (📦small)

**Files:**
- `NEW:` `src/builderpulse/infra/secrets.py`
- `NEW:` `tests/test_secrets.py`

**依赖:** T4

- [ ] **Step 1: Write tests** — keyring fallback to secrets.json(600), env var priority, masking
- [ ] **Step 2: Run tests → FAIL**
- [ ] **Step 3: Implement secrets.py** — keyring → secrets.json → env var 三级降级
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

## Phase 2: Infrastructure (from douyin_batch)

### Task 6: infra/* — 基础设施移植 (📦small)

**Files:**
- `NEW:` `src/builderpulse/infra/i18n.py` — 从 douyin_batch/i18n.py 移植
- `NEW:` `src/builderpulse/infra/security.py` — 从 douyin_batch/security.py 移植
- `NEW:` `src/builderpulse/infra/platform_compat.py` — 从 douyin_batch/platform_compat.py 移植
- `NEW:` `src/builderpulse/infra/progress.py` — 从 douyin_batch/progress.py 移植，改用 rich
- `NEW:` `tests/test_infra.py`

**依赖:** T4

- [ ] **Step 1: Read source files** from `D:/1/video2text/douyin_batch/`
- [ ] **Step 2: Port each module** — 调整 import 路径，移除对 douyin_batch 的依赖
- [ ] **Step 3: Create `tests/conftest.py`** — 统一 mock fixtures：

```python
# tests/conftest.py
import pytest
import respx  # pip install respx

@pytest.fixture
def mock_httpx():
    """Intercept all httpx requests in tests."""
    with respx.mock:
        yield respx

@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Redirect state.db to temp dir for test isolation."""
    monkeypatch.setenv("BUILDERPULSE_STATE_DB", str(tmp_path / "state.db"))
```
- [ ] **Step 4: Write tests** — 覆盖 i18n 切换、URL 安全检查、文件名清理、进度条
- [ ] **Step 5: Run tests → PASS**
- [ ] **Step 6: Commit**

---

## Phase 3: Engines (from video2text)

### Task 7: engines/downloaders/base.py — 下载器抽象 (⚡micro)

**Files:**
- `NEW:` `src/builderpulse/engines/__init__.py`
- `NEW:` `src/builderpulse/engines/downloaders/__init__.py`
- `NEW:` `src/builderpulse/engines/downloaders/base.py`

**依赖:** T2

- [ ] **Step 1: Port from `D:/1/video2text/video2text/downloaders/base.py`** — 调整 import
- [ ] **Step 2: Verify import works**
- [ ] **Step 3: Commit**

---

### Task 8: engines/downloaders/yt_dlp.py — yt-dlp 下载器 (📦small)

**Files:**
- `NEW:` `src/builderpulse/engines/downloaders/yt_dlp.py`
- `NEW:` `tests/test_downloaders.py`

**依赖:** T7

- [ ] **Step 1: Port from `D:/1/video2text/video2text/downloaders/ytdlp.py`**
- [ ] **Step 2: Write tests** — mock yt-dlp 调用，验证参数传递
- [ ] **Step 3: Run tests → PASS**
- [ ] **Step 4: Commit**

---

### Task 9: engines/downloaders/bilibili.py — B站下载器 + WBI 签名 (📦small)

**Files:**
- `NEW:` `src/builderpulse/engines/downloaders/bilibili.py`
- `NEW:` `tests/test_bilibili_downloader.py`

**依赖:** T7

- [ ] **Step 1: Read sources** — `D:/1/video2text/video2text/downloaders/douyin.py`(Playwright 部分)。WBI 签名算法从 bilibili.js **手工移植为纯 Python**（MD5 + MIXIN_KEY_ENC_TAB 查表），不依赖 Node.js
- [ ] **Step 2: Implement** — 纯 Python WBI 签名 + Playwright(Python) fallback + cookie 模式
- [ ] **Step 3: Write tests** — mock B站 API，验证签名计算
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

### Task 10: engines/downloaders/douyin.py — 抖音下载器 (📦small)

**Files:**
- `NEW:` `src/builderpulse/engines/downloaders/douyin.py`

**依赖:** T7

- [ ] **Step 1: Port from `D:/1/video2text/video2text/downloaders/douyin.py`** — Playwright 拦截 douyinvod.com
- [ ] **Step 2: Adjust imports** to builderpulse path
- [ ] **Step 3: Commit**

---

### Task 11: engines/transcribers/* — 转录引擎 (📦small)

**Files:**
- `NEW:` `src/builderpulse/engines/transcribers/__init__.py` — get_transcriber() auto-detect
- `NEW:` `src/builderpulse/engines/transcribers/base.py`
- `NEW:` `src/builderpulse/engines/transcribers/whisper.py`
- `NEW:` `src/builderpulse/engines/transcribers/whisperx.py`
- `NEW:` `src/builderpulse/engines/transcribers/faster_whisper.py`

**依赖:** T2

- [ ] **Step 1: Port all from `D:/1/video2text/video2text/transcribers/`**
- [ ] **Step 2: Implement get_transcriber()** — auto-detect: faster-whisper > whisperx > whisper
- [ ] **Step 3: Verify imports** (no Whisper installed → graceful ImportError message)
- [ ] **Step 4: Commit**

---

### Task 12: core/pipeline.py — 核心流水线 (🏗️large)

**Files:**
- `NEW:` `src/builderpulse/core/pipeline.py`
- `NEW:` `tests/test_pipeline.py`

**依赖:** T2, T3, T7-T11, T1

- [ ] **Step 1: Port from `D:/1/video2text/video2text/pipeline.py`**
- [ ] **Step 2: Implement Pipeline with composable steps** — 支持任意步骤组合：

```python
class Pipeline:
    def __init__(self, config: Config, state: State):
        self.config = config
        self.state = state
        self.steps: list[Callable] = []

    def add(self, step: Callable) -> "Pipeline":
        self.steps.append(step)
        return self

    def run(self, source: SourceRef) -> dict:
        ctx = {"source": source, "config": self.config, "state": self.state}
        for step in self.steps:
            ctx = step(ctx)
            if ctx.get("error"):
                break
        return ctx

# 预定义步骤
def step_download(ctx): ...    # engines/downloaders/*
def step_transcribe(ctx): ...  # engines/transcribers/*
def step_summarize(ctx): ...   # remix/summarizer.py
def step_translate(ctx): ...   # remix/translator.py
def step_deliver(ctx): ...     # deliver/*
```

CLI 中 `bp process --steps transcribe,summarize,deliver=telegram` 动态构建。
- [ ] **Step 3: Write tests** — mock downloader + transcriber，验证完整流程 + 步骤组合 + 错误中断
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

## Phase 4: Content Sources (JS → Python rewrite)

### Task 13: sources/podcast.py — 播客 RSS (📦small)

**Files:**
- `NEW:` `src/builderpulse/sources/__init__.py`
- `NEW:` `src/builderpulse/sources/podcast.py`
- `NEW:` `tests/test_sources.py`

**依赖:** T2, T3

- [ ] **Step 1: Read `C:/Users/12739/.claude/skills/follow-builders/scripts/generate-feed.js`** — RSS 解析部分
- [ ] **Step 2: Rewrite in Python** — feedparser + httpx + pod2txt transcript fetch
- [ ] **Step 3: Write tests** — mock RSS feed，验证解析 + 去重
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

### Task 14: sources/blog.py — 博客抓取 (📦small)

**Files:**
- `NEW:` `src/builderpulse/sources/blog.py`

**依赖:** T2, T3

- [ ] **Step 1: Read generate-feed.js** — blog scraping 部分（Anthropic + Claude Blog）
- [ ] **Step 2: Rewrite** — httpx + BeautifulSoup4，支持 __NEXT_DATA__ JSON + HTML fallback
- [ ] **Step 3: Commit**

---

### Task 15: sources/twitter.py — X/Twitter (📦small)

**Files:**
- `NEW:` `src/builderpulse/sources/twitter.py`

**依赖:** T2, T3

- [ ] **Step 1: Implement tweepy wrapper** — API v2 batch lookup + tweet fetch
- [ ] **Step 2: Add Nitter RSS fallback** — 无 token 时降级
- [ ] **Step 3: Commit**

---

### Task 16: sources/bilibili.py + youtube.py — B站 + YouTube (📦small)

**Files:**
- `NEW:` `src/builderpulse/sources/bilibili.py` — Bilibili API + WBI（与 engines 的 bilibili.py 共享签名逻辑）
- `NEW:` `src/builderpulse/sources/youtube.py` — YouTube RSS + feedparser

**依赖:** T2, T3

- [ ] **Step 1: Implement bilibili.py** — 用户视频列表 API + WBI 签名
- [ ] **Step 2: Implement youtube.py** — channel RSS + feedparser
- [ ] **Step 3: Commit**

---

## Phase 5: Remix (LLM 摘要)

### Task 17: remix/* — LLM 摘要 + 翻译 (📦small)

**Files:**
- `NEW:` `src/builderpulse/remix/__init__.py`
- `NEW:` `src/builderpulse/remix/prompts.py` — 加载 prompt 模板（custom overrides builtin）
- `NEW:` `src/builderpulse/remix/summarizer.py` — LLM adapter (OpenAI/Anthropic/Ollama) + Map-Reduce 分块
- `NEW:` `src/builderpulse/remix/translator.py`

**依赖:** T3

- [ ] **Step 1: Copy prompts** from `C:/Users/12739/.claude/skills/follow-builders/prompts/`
- [ ] **Step 2: Implement prompts.py** — custom > builtin 加载策略
- [ ] **Step 3: Implement summarizer.py** — LLMProvider ABC + 3 个实现 + Map-Reduce
- [ ] **Step 4: Implement translator.py**
- [ ] **Step 5: Commit**

---

## Phase 6: Delivery Channels

### Task 18: deliver/* — 多渠道投递 (📦small)

**Files:**
- `NEW:` `src/builderpulse/deliver/__init__.py`
- `NEW:` `src/builderpulse/deliver/base.py` — DeliveryChannel ABC
- `NEW:` `src/builderpulse/deliver/telegram.py`
- `NEW:` `src/builderpulse/deliver/email_sender.py` — SMTP + Resend
- `NEW:` `src/builderpulse/deliver/stderr_fallback.py`
- `NEW:` `src/builderpulse/deliver/wechat.py` — PushPlus/Server酱/WxPusher
- `NEW:` `src/builderpulse/deliver/lark.py` — 飞书 Webhook
- `NEW:` `src/builderpulse/deliver/dingtalk.py` — 钉钉 Webhook
- `NEW:` `src/builderpulse/deliver/wecom.py` — 企业微信 Webhook
- `NEW:` `src/builderpulse/deliver/discord.py` — Discord Webhook
- `NEW:` `tests/test_deliver.py`

**依赖:** T4

- [ ] **Step 1: Implement base.py** — ABC + send() + name + _chunk_markdown()
- [ ] **Step 2: Implement each channel** — 每个渠道一个文件，httpx 调用
- [ ] **Step 3: Write tests** — mock httpx，验证 payload 格式、分片、重试
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

## Phase 7: Access Layer (CLI + MCP)

### Task 19: cli.py — CLI 入口 (🏗️large)

**Files:**
- `NEW:` `src/builderpulse/cli.py`
- `NEW:` `tests/test_cli.py`

**依赖:** T3, T4, T5, T6, T12, T17, T18

- [ ] **Step 1: Implement click groups** — transcribe / batch / digest / fetch / process / clean / config / serve / config reload
- [ ] **Step 2: Wire up core modules** — 每个命令调用对应的 core 函数
- [ ] **Step 3: Write tests** — click.testing.CliRunner，验证命令解析
- [ ] **Step 4: Run tests → PASS**
- [ ] **Step 5: Commit**

---

### Task 20: mcp_server.py — MCP Server (📦small)

**Files:**
- `NEW:` `src/builderpulse/mcp_server.py`
- `NEW:` `tests/test_mcp.py`

**依赖:** T3, T12, T17

- [ ] **Step 1: Implement MCP tools** — bp_transcribe / bp_batch_transcribe / bp_digest / bp_process / bp_fetch_feed / bp_list_sources / bp_config / bp_reload_config
- [ ] **Step 2: Add progress notifications** — notifications/progress for long operations
- [ ] **Step 3: Add cancellation support** — 检查 `token.is_cancelled`，取消时终止子进程(yt-dlp/whisper)并清理临时文件。使用 `asyncio.wait_for` 包裹耗时操作
- [ ] **Step 4: Add bp_reload_config** — 运行时重新加载 `~/.builderpulse/config.json`，无需重启 MCP server
- [ ] **Step 5: Write tests** — mock MCP client，验证 tool 注册 + 调用 + 取消 + 配置重载
- [ ] **Step 6: Run tests → PASS**
- [ ] **Step 7: Commit**

---

## Phase 8: Migration + Config + CI

### Task 21: 迁移脚本 (📦small)

**Files:**
- `NEW:` `src/builderpulse/migrate.py` — follow-builders / video2text → builderpulse 迁移
- `NEW:` `tests/test_migrate.py`

**依赖:** T1, T3

- [ ] **Step 1: Implement** — 解析 follow-builders state.json → feed_cursors + processed_items；扫描 video2text output/ → processed_items
- [ ] **Step 2: Write tests** — mock 老文件格式
- [ ] **Step 3: Commit**

---

### Task 22: pyproject.toml 完善 (⚡micro)

**Files:**
- `EXISTS:` `pyproject.toml` — 补全所有 optional-dependencies

**依赖:** 无（独立任务）

- [ ] **Step 1: 更新 pyproject.toml** — 添加所有 extras：

```toml
[project.optional-dependencies]
whisper = ["openai-whisper>=20231117", "torch>=2.0"]
whisperx = ["whisperx>=3.1.1", "torch>=2.0", "pyannote.audio>=3.0"]
faster-whisper = ["faster-whisper>=0.10"]
browser = ["playwright>=1.40"]
sources = ["feedparser>=6.0", "beautifulsoup4>=4.12", "tweepy>=4.14"]
llm = ["openai>=1.0", "anthropic>=0.20", "ollama>=0.1"]
mcp = ["mcp>=1.0"]
secrets = ["keyring>=23.0"]
cpu = ["openai-whisper>=20231117", "torch>=2.0 --index-url https://download.pytorch.org/whl/cpu"]
dev = ["pytest>=7.4", "pytest-cov>=4.1", "ruff>=0.1", "respx>=0.21"]
```
- [ ] **Step 2: Verify** — `pip install builderpulse[llm,secrets,dev]` 无冲突
- [ ] **Step 3: Commit**

---

### Task 23: GitHub Actions CI (📦small)

**Files:**
- `NEW:` `.github/workflows/test.yml` — CI 矩阵
- `NEW:` `.github/workflows/generate-feed.yml` — 定时 feed 更新
- `NEW:` `.gitignore`
- `NEW:` `README.md`
- `NEW:` `README.zh-CN.md`
- `NEW:` `LICENSE` — MIT

**依赖:** T22

- [ ] **Step 1: Create test.yml** — Python 3.9-3.12 × Ubuntu/macOS/Windows，pytest + ruff + i18n check
- [ ] **Step 2: Create generate-feed.yml** — cron daily 6:17am UTC
- [ ] **Step 3: Create README.md + README.zh-CN.md** — Quick Start / Supported Sources / Agent Integration
- [ ] **Step 4: Commit**

**CI 额外检查（Issue #6 i18n 覆盖）：**
```yaml
# test.yml 中增加一步
- name: Check i18n coverage
  run: |
    # 禁止裸 print()（允许 logger 和 tests）
    ! grep -rn "print(" src/builderpulse/ --include="*.py" | grep -v "logger\|# noqa\|__pycache__"
    # 验证所有用户可见字符串经过 i18n 包装
    python -c "from builderpulse.infra.i18n import t; assert t('MISSING_KEY', default='ok') == 'ok'"
```

---

## Phase 9: Verification

### Task 24: E2E 验证 (📦small)

**Files:** 无新建，验证现有功能

**依赖:** T19, T20

- [ ] **Step 1: CLI smoke test** — `PYTHONPATH=src python -m builderpulse.cli --help`
- [ ] **Step 2: State integration** — `PYTHONPATH=src python -c "from builderpulse.core.state import State; s = State(); print(s.stats())"`
- [ ] **Step 3: MCP tool registration** — `PYTHONPATH=src python -c "from builderpulse.mcp_server import tools; print([t['name'] for t in tools])"`
- [ ] **Step 4: Offline E2E transcribe test** — 使用本地音频文件：

```bash
# 准备测试音频（10秒静音 WAV，用于验证管道不崩溃）
python -c "
import wave, struct
with wave.open('tests/fixtures/sample.wav','w') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
    f.writeframes(struct.pack('<'+'h'*160000, *([0]*160000)))
"
# 运行转录（如果 whisper 已安装）
PYTHONPATH=src python -m builderpulse.cli transcribe tests/fixtures/sample.wav --engine auto --output stdout
# 或仅验证管道不崩溃（无 whisper 时）
PYTHONPATH=src python -c "
from builderpulse.core.pipeline import Pipeline
from builderpulse.core.models import SourceRef
p = Pipeline(config=None, state=None)
print('Pipeline steps:', len(p.steps))
"
```
- [ ] **Step 5: Full test suite** — `PYTHONPATH=src python -m pytest tests/ -v`
- [ ] **Step 6: Commit final state**
