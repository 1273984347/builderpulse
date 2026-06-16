# BuilderPulse

> 不再手动刷 10+ 个网站追 AI builder 动态。一条命令，全部送达。

[English](README.md) | [简体中文](README.zh-CN.md)

**之前（每天 30+ 分钟）：**
```
1. 打开 YouTube → 检查 5 个频道 → 复制链接
2. 打开 B 站 → 检查 3 个 UP 主 → 复制链接
3. 打开 X/Twitter → 刷时间线
4. 打开播客 App → 检查新节目
5. 打开 3 个博客 RSS → 看标题
6. 手动整理感兴趣的内容
7. 发到自己 Telegram
```

**之后（30 秒）：**
```bash
bp digest --lang zh --deliver telegram
# 8 个工具，0 手动操作。
```

---

## 功能

| 能力 | 实现方式 |
|:-----|:---------|
| **转录** 任意视频为文字 | YouTube、B站、抖音、1000+ 站点（yt-dlp） |
| **聚合** AI builder 内容 | X/Twitter、播客、博客、B站、YouTube |
| **摘要** 使用 LLM | OpenAI、Anthropic、Ollama — 自动检测 |
| **投递** 到你的渠道 | Telegram、飞书、钉钉、Discord、邮件、微信 |
| **MCP Server** | 适配 Claude Code、Cursor、Continue 等 AI Agent |
| **批量处理** | SQLite 缓存、断点续传、限流、磁盘守护 |
| **可观测性** | OpenTelemetry 集成，链路追踪 + 指标 |
| **插件系统** | 基于 entry_points 的可扩展架构 |

## 快速开始

```bash
# 安装
pip install builderpulse

# 转录视频
bp transcribe "https://www.bilibili.com/video/BV1xxx"

# 生成摘要（全源、中文、投递到 Telegram）
bp digest --lang zh --deliver telegram

# 批量转录创作者
bp batch "https://space.bilibili.com/123456" --limit 20 --summarize

# 作为 MCP 工具使用（Claude Code / Cursor）
bp serve
```

## 如何使用 BuilderPulse

BuilderPulse 提供 **4 种使用方式**，每种适合不同场景。根据你的需求选一种。

### 1. 💻 CLI — 临时命令和定时任务

**适用场景**：想跑一条快速命令、cron 任务、临时任务。除了 `pip install` 之外无需任何配置。

#### 每日早间摘要（杀手级用例）

```bash
bp digest --lang zh --deliver telegram
# → 从所有源抓取，调用你的 LLM 摘要，发送到 Telegram
# 大约 30 秒搞定
```

用 `cron` / `Task Scheduler` 定时在每天早上 8 点触发。示例见 [docs/scheduling.md](docs/scheduling.md)。

#### 转录刚发现的单个视频

```bash
bp transcribe "https://www.bilibili.com/video/BV1xxxx" --engine faster-whisper
# → 下载、转录（如需）、保存 markdown 到 ./output/
```

#### 追完某个 UP 主的全部更新（断点续传）

```bash
bp batch "https://space.bilibili.com/123456" --limit 20 --summarize
# → 处理 20 个视频。中断（Ctrl+C）后再跑，从断点续跑。
# SQLite 缓存保证同一 URL 不会被重复处理。
```

#### 查看或修改配置

```bash
bp config show                    # 查看所有设置（密钥自动脱敏）
bp config init                    # 生成一份 config.json 模板
```

---

### 2. 🤖 MCP Server — 接入 AI Agent（Claude Code、Cursor 等）

**适用场景**：想让你的 AI Agent 对话式地帮你抓取 / 转录 / 摘要。

#### Claude Code 配置（`~/.claude.json` 或 `.mcp.json`）

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

重启 Claude Code 后，你会看到 6 个新工具：`bp_transcribe`、`bp_digest`、`bp_process`、`bp_fetch_feed`、`bp_list_sources`、`bp_config`。

#### 对话中的效果

```
你：   "给我一份昨天的 AI builder 摘要，中文版，发送到我的 Telegram"
Agent：[调用 bp_digest] → ✓ 已送达
```

#### Cursor / Continue / Windsurf 配置

同样的 JSON 配置即可。`bp serve` 子进程通过 stdio 跑 JSON-RPC 2.0，所有 MCP 客户端都能识别。

---

### 3. 🐍 Python API — 嵌入到你自己的代码

**适用场景**：你在做定制工具、仪表盘、自动化，需要用 BuilderPulse 的零件但不要 CLI/MCP 层。

```python
from builderpulse.sources.youtube import YouTubeSource
from builderpulse.remix.summarizer import Summarizer
from builderpulse.deliver import get_channel

# 从源抓取
src = YouTubeSource()
items = src.fetch(limit=10, days=7)

# 摘要
summarizer = Summarizer(llm="claude")  # 或 "openai"、"ollama"
for item in items:
    item.summary = summarizer.summarize(item.content)

# 投递
ch = get_channel("telegram")
ch.send(format_digest(items), title="My Daily Digest")
```

每个模块（`sources/`、`remix/`、`deliver/`）都可以独立导入。完整接口见 [docs/api.md](docs/api.md)。

---

### 4. 🔌 插件系统 — 添加你自己的源 / 投递渠道

**适用场景**：内置的 6 个源或 8 个投递渠道满足不了你的需求。

在 `pyproject.toml` 里挂一个带 entry-point 的 Python 文件：

```toml
[project.entry-points."builderpulse.sources"]
my_custom_source = "my_pkg.source:MySource"
```

你的类只需要满足一个 `Protocol`（源的 `fetch` 方法、渠道的 `deliver` 方法），就会自动出现在 `bp fetch` / `bp digest` / `bp serve` 里。完整契约见 [docs/plugins.md](docs/plugins.md)。

---

### 5. ✨ 作者本人的使用方式

下面三种是我日常使用 BuilderPulse 的方式，覆盖了约 95% 的使用场景。

#### 🌅 每日早间摘要（每天必跑）

每个工作日早上 8:05，我家用 Windows 的 Task Scheduler 触发 `bp digest`。结果在我喝咖啡时就送到 Telegram 了，我在通勤路上读。

```cmd
schtasks /create /tn "BuilderPulse Morning" /tr "bp digest --lang zh --sources podcast,youtube,bilibili,blog --deliver telegram" /sc daily /st 08:05
```

端到端大约 25 秒。如果看到感兴趣的内容，直接从 Telegram 点源链接。

#### 🤖 在 Claude Code 里（工作时）

我在 Claude Code 里把 `bp serve` 作为 MCP 工具挂着。写代码时想知道"这个 builder 这周发了什么"，直接问：

```
> 抓取我在关注的这个创作者这周的 B 站视频，摘要其中最值得看的一条
```

Claude Code 调 `bp_fetch_feed` → `bp_digest` → 返回一段一段话的摘要。无须切换上下文、无须复制粘贴。

```json
// ~/.claude.json
{
  "mcpServers": {
    "builderpulse": { "command": "bp", "args": ["serve"] }
  }
}
```

#### 📚 周六补清单（断点续传）

周六早上第二杯咖啡时，我对某个落下一堆更新的创作者跑 `bp batch`：

```bash
bp batch "https://space.bilibili.com/123456" --limit 30 --summarize --engine faster-whisper
```

处理 30 个视频。如果周六有事被打断，`Ctrl+C`。下周六再跑，从 SQLite 缓存的视频 14 续跑，不会重下。`--engine faster-whisper` 意味着不用 GPU，CPU 也能跑。

---

**你呢？** 欢迎开 issue 或 PR 分享你的使用场景 — 最好的文档来自真实工作流。

---

## 选择合适的方法

| 场景 | 用什么 |
|:-----|:-------|
| "我只想今天的摘要送到我 Telegram" | **CLI**（`bp digest`） |
| "我想每天早上 8 点自动跑" | **CLI** + cron / Task Scheduler |
| "我的 AI Agent 帮我做" | **MCP**（Claude Code / Cursor） |
| "我要在它上面做定制工具" | **Python API** |
| "我需要新源 / 新投递渠道" | **插件** |
| "我要追 100 个视频" | **CLI**（`bp batch`，断点续传） |

---

## 典型 pipeline 怎么跑

```
[源] → [下载器] → [转录器] → [摘要器] → [投递渠道]
 ↓        ↓         ↓          ↓           ↓
YouTube  yt-dlp   faster-whisper  Claude   Telegram
B站      API+playwright  WhisperX   GPT-4    Email
播客     RSS+asr   OpenAI Whisper  Ollama   Discord
博客     html 抓取
Twitter  API v2 / Nitter
```

每一步独立。某一步失败时，错误会带着类型化错误码被捕获，流水线继续往下走。详见 [docs/error-codes.md](docs/error-codes.md)。

## 安装

```bash
pip install builderpulse                    # 核心
pip install builderpulse[whisper]           # + OpenAI Whisper
pip install builderpulse[faster-whisper]    # + faster-whisper（推荐 CPU）
pip install builderpulse[whisperx]          # + WhisperX（最佳质量，需 GPU）
pip install builderpulse[browser]           # + Playwright（B站/抖音浏览器模式）
pip install builderpulse[sources]           # + feedparser + tweepy + BeautifulSoup
pip install builderpulse[llm]               # + OpenAI + Anthropic + Ollama SDK
pip install builderpulse[secrets]           # + keyring 安全凭证存储
```

## 配置

BuilderPulse 读一个 JSON 配置文件。默认路径 `~/.builderpulse/config.json`，也可以用 `BUILDERPULSE_CONFIG_PATH` 环境变量覆盖（12-factor app 约定）。

```bash
# 1. 把示例配置复制到家目录
mkdir -p ~/.builderpulse
cp config.example.json ~/.builderpulse/config.json

# 2. 编辑你自己的源、账号、渠道凭证
$EDITOR ~/.builderpulse/config.json
```

### `config.example.json` 里有什么

- **`enabled_sources`** / **`enabled_channels`** — 启用哪些内置插件
- **`sources.{podcast,twitter,blog,bilibili,youtube}`** — 每个源的配置
  - `podcast.feeds`：RSS feed URL 列表
  - `twitter.accounts`：X/Twitter 账号列表（需要 `X_BEARER_TOKEN` 环境变量）
  - `blog.urls`：要抓取的博客 URL 列表
  - `bilibili.users`：B站用户 ID 列表（数字）
  - `youtube.channels`：YouTube 频道 ID 列表（`UC...`）
- **空列表 = "跳过这个源"** — 你的 cron 照样跑，只是这个源不抓取

### 可选环境变量

| 变量 | 作用 | 是否必需 |
|:-----|:-----|:---------|
| `X_BEARER_TOKEN` | X/Twitter API v2 bearer token。没有它，`twitter.accounts` 会被静默跳过 | 否（仅 Twitter 需要） |
| `BUILDERPULSE_CONFIG_PATH` | 覆盖默认配置位置（`~/.builderpulse/config.json`） | 否 |
| `BUILDERPULSE_TELEGRAM_BOT_TOKEN`、`BUILDERPULSE_TELEGRAM_CHAT_ID` 等 | 各渠道凭证（覆盖 JSON 文件里的值） | 否（用对应渠道时才需要） |

### 隐私

本仓库的 `config.example.json` 只发 **空列表** — 你的个人源和 token 不应该（也永远不要）提交。用环境变量或本地 `~/.builderpulse/config.json`（默认在 .gitignore 里）来存凭证。

## 支持的源

| 源 | 引擎 | 需要 API Key |
|:---|:-----|:-------------|
| YouTube / 1000+ 站 | yt-dlp | 否 |
| B站 | API + WBI 签名 | 否（SESSDATA 可选） |
| 抖音 | Playwright | 否 |
| X/Twitter | API v2 / Nitter RSS | 可选 |
| 播客 | RSS + 转录 | 否 |
| 博客 | HTML 抓取 | 否 |

## Agent 集成

BuilderPulse 支持所有兼容 MCP 协议的 AI Agent。

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

或使用 skill：`/builderpulse`

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

## MCP 工具

| 工具 | 说明 |
|:-----|:-----|
| `bp_transcribe` | 转录视频/音频为文字 |
| `bp_batch_transcribe` | 批量转录创作者视频 |
| `bp_digest` | 生成 AI builder 摘要 |
| `bp_process` | 端到端流水线 |
| `bp_fetch_feed` | 抓取原始内容 |
| `bp_list_sources` | 列出配置的源 |
| `bp_config` | 查看/修改配置（密钥自动脱敏） |
| `bp_reload_config` | 热重载配置 |

## CLI 命令

```bash
bp transcribe <url>              # 单视频转录
bp batch <user_url> --limit 20   # 批量转录（断点续传）
bp digest --sources podcast,blog # 生成摘要
bp fetch bilibili --user <mid>   # 抓取原始内容
bp process <url> --summarize     # 端到端流水线
bp clean                         # 清理旧文件
bp config show                   # 查看配置
bp config set <key> <value>      # 设置配置项
bp config reload                 # 热重载配置
bp serve                         # 启动 MCP Server
```

## 架构

```
builderpulse/
├── src/builderpulse/
│   ├── core/          # 配置、状态（SQLite）、流水线、模型、错误码
│   ├── engines/       # 下载器（yt-dlp、B站、抖音）+ 转录引擎
│   ├── sources/       # 内容聚合（播客、博客、推特、B站、YouTube）
│   ├── remix/         # LLM 摘要 + 翻译
│   ├── deliver/       # 8 个投递渠道
│   ├── batch/         # 批量处理（缓存、磁盘守护、限流器）
│   ├── plugins/       # 插件注册表（基于 entry_points）
│   ├── infra/         # 日志、安全、国际化、可观测性、性能分析
│   ├── cli.py         # CLI 入口
│   └── mcp_server.py  # MCP Server（JSON-RPC over stdio）
├── tests/             # 449 个测试
├── prompts/           # LLM prompt 模板
├── docs/              # 架构文档、插件开发指南、迁移指南
└── .claude-plugin/    # Claude Code 插件清单
```

### 核心设计模式

| 模式 | 位置 | 用途 |
|:-----|:-----|:-----|
| **插件注册表** | `plugins/` | 基于 `importlib.metadata.entry_points()` 的可扩展架构 |
| **ConfigManager** | `core/config_manager.py` | 线程安全单例 + 热重载 |
| **重试 + 降级** | `batch/retry.py` | 指数退避 + 完整尝试历史 |
| **错误码** | `core/error_codes.py` | 程序化错误识别 |
| **Agent 输出** | `infra/agent_output.py` | 版本化 JSON schema（MCP 兼容） |
| **可观测性** | `infra/observability.py` | OpenTelemetry span + 指标 |
| **SQLite WAL** | `core/state.py`、`batch/cache.py` | 并发读写 + 崩溃恢复 |

## 数据

- **90+ 个文件** / 12,000+ 行 Python
- **449 个测试** 全部通过
- **8 个 MCP 工具** 适配 AI Agent
- **8 个投递渠道**（Telegram、飞书、钉钉、Discord、邮件、微信、企业微信、stderr）
- **5 个内容源**（X/Twitter、播客、博客、B站、YouTube）
- **3 个转录引擎**（Whisper、WhisperX、faster-whisper）
- **零 Node.js 依赖** — 纯 Python

## 文档

- [架构概览](docs/architecture.md)
- [插件开发指南](docs/plugins.md)
- [错误码参考](docs/error-codes.md)
- [v1 → v2 迁移指南](docs/migration-v2.md)

## 许可证

MIT
