---
name: blog-builderpulse-zh
description: "技术博客: BuilderPulse — AI 内容聚合平台的技术架构"
type: spec
metadata:
  created: 2026-06-27
  platform: 掘金
  language: zh
  status: draft
---

# BuilderPulse — AI 内容聚合平台的技术架构

> 9 个内容源 + 12 个推送渠道 + MCP Server + RAG 检索，一个命令搞定。

## 背景

每天手动检查 10+ 个网站获取 AI builder 更新？太累了。

BuilderPulse 是一个 AI 内容聚合平台，一条命令搞定所有：

```bash
bp digest --lang zh --deliver telegram
# 30 秒完成。9 个源，0 手动操作。
```

## 技术架构

### 1. 数据采集层

| 源 | 技术 | 说明 |
|:---|:-----|:-----|
| YouTube | yt-dlp | 1000+ 网站视频下载 |
| Bilibili | yt-dlp | B 站视频 |
| X/Twitter | Nitter | 推文抓取 |
| Podcast | feedparser | RSS 订阅 |
| Blog | requests + BeautifulSoup | 网页抓取 |

### 2. 处理层

```
下载 → 转录 → 摘要 → 翻译 → 推送
```

- **转录**: faster-whisper (PyTorch, 支持中英文)
- **摘要**: Claude API (双模式: AI + 模板回退)
- **翻译**: Claude API (中英文互译)
- **推送**: 12 个渠道 (飞书/邮箱/Telegram/Discord/Slack/WeChat 等)

### 3. MCP Server

BuilderPulse 实现了 MCP (Model Context Protocol)，可以被 Claude Code、Cursor、Continue 等 AI agent 调用：

```python
# 7 个 MCP tools
bp_transcribe    # 视频转录
bp_digest        # 内容聚合
bp_process       # 端到端管道
bp_fetch_feed    # 原始内容获取
bp_list_sources  # 列出所有源
bp_config        # 查看配置
bp_search_similar # RAG 检索 (新增)
bp_generate_response # LLM 生成 (新增)
```

### 4. RAG 检索

BuilderPulse 实现了 Qdrant 向量检索 + BM25 + Claude 重排的混合检索：

```python
from builderpulse.rag.channel import RAGChannel

channel = RAGChannel(collection="builderpulse")
results = channel.search_hybrid("AI agent architecture", top_k=10)
```

### 5. 缓存层

支持内存缓存 + Redis 缓存 (可切换)：

```python
from builderpulse.infra.cache import Cache

cache = Cache(redis_url="redis://localhost:6379")  # Redis
cache = Cache()  # 内存
cache.set("key", "value", ttl=3600)
```

## 关键设计决策

1. **CLI + MCP 双接口**: 命令行用户 + AI agent 都能用
2. **12 个推送渠道**: 飞书/邮箱/Telegram/Discord/Slack/WeChat/DingTalk/Notion/Bark/Stderr/Webhook/WeCom
3. **BatchCache WAL**: SQLite WAL 模式保证数据一致性
4. **dependabot**: 自动依赖更新 + 安全漏洞修复
5. **CI 9/9 matrix**: GitHub Actions 自动化测试

## 版本历史

| 版本 | 日期 | 关键功能 |
|:-----|:-----|:---------|
| v2.0.0 | 2026 Q1 | 初始版本 |
| v2.2.0 | 2026-06-27 | LightRAG roles + source registry + prompt registry |
| v2.3.0 | 2026-06-27 | MCP +2 tools + RAG hybrid search + cache layer |

## 代码仓库

https://github.com/1273984347/builderpulse

---

*BuilderPulse — AI 内容聚合平台的技术架构*
*Penelope · 织网笔记*
*Weaving and unweaving.*
