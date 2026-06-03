# BuilderPulse

> 追踪 AI builder 的动态 — 转录、摘要、投递一站式工具。

**v1.0.0**

## 功能

- **转录** 任意视频/音频为文字（B站/抖音/YouTube/1000+ 站点）
- **聚合** AI builder 内容（X/Twitter、播客、博客、B站）
- **摘要** 使用 LLM 生成结构化摘要
- **投递** 到 Telegram、邮件、飞书、钉钉、Discord 等
- **MCP Server** — 从 Claude Code、Cursor 或任何 AI agent 调用

## 快速开始

```bash
pip install builderpulse

# 转录视频
bp transcribe "https://www.bilibili.com/video/BV1xxx"

# 生成摘要
bp digest --lang zh --deliver telegram

# 作为 MCP 工具使用
bp serve
```

## 安装

```bash
pip install builderpulse                    # 核心
pip install builderpulse[faster-whisper]    # + faster-whisper（推荐 CPU）
pip install builderpulse[browser]           # + Playwright（B站/抖音浏览器模式）
pip install builderpulse[llm]               # + LLM SDK（OpenAI/Anthropic/Ollama）
```

## 支持的源

| 源 | 引擎 | 需要 API Key |
|----|------|-------------|
| YouTube / 1000+ 站 | yt-dlp | 否 |
| B站 | API + WBI 签名 | 否（SESSDATA 可选） |
| 抖音 | Playwright | 否 |
| X/Twitter | API v2 / Nitter RSS | 可选 |
| 播客 | RSS + 转录 | 否 |
| 博客 | HTML 抓取 | 否 |

## Agent 集成

BuilderPulse 支持所有兼容 MCP 协议的 AI Agent。

### Claude Code

添加到 `.claude/settings.json`：
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

或使用 Claude Code skill：`/builderpulse`

### Cursor

添加到 `.cursor/mcp.json`：
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

添加到 `~/.continue/config.json`：
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

使用 `builderpulse-mcp` 入口：
```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "builderpulse-mcp"
    }
  }
}
```

### MCP 入口

```bash
builderpulse-mcp          # 直接启动 MCP server
bp serve                  # 同上，通过 CLI
python -m builderpulse serve  # 同上，通过 Python 模块
```
