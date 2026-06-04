# BuilderPulse

> 不再手动刷 10+ 个网站追 AI builder 动态。一条命令，全部送达。

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
