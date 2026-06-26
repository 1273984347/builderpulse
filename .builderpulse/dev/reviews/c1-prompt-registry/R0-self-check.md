# R0 — Self-Check (Commit 1: RolePromptRegistry)

> **范围**: 接通 prompt 模板 (`RolePromptRegistry` + `step_summarize` 改造)
> **时间**: 2026-06-26 (人工 inline ~5 min)

## 改动文件

| 文件 | 类型 | 行数 |
|:--|:--|:--:|
| `src/builderpulse/remix/prompt_registry.py` | 新增 | 96 |
| `src/builderpulse/core/pipeline.py` | 修改 `step_summarize` | +18 / -1 |
| `tests/test_prompt_registry.py` | 新增 | 145 |
| `tests/test_pipeline_remix.py` | 补充 3 用例 | +85 |

**总**: +344 行（其中 ~80% 是测试）

## 单点检查 (✓ = pass)

- [x] **commit 单一关注点**: 仅改 "接通模板"，未触及 token 计量 / 异常分类
- [x] **L1 单测 16/16 pass**: `test_prompt_registry.py` (6) + `test_pipeline_remix.py` (10 含新增 3)
- [x] **全量回归 609 pass / 4 skipped / 0 fail** (166s)
- [x] **不破坏现有 signature**: `AnthropicProvider.complete()` 未改；`step_summarize` 仍接受 `ctx`
- [x] **graceful degradation**: 模板全缺 → `system=""` 不挂
- [x] **3-tier 优先级**: custom_dir > builtin > default fallback

## 自我 P0 发现

无 P0 阻断。1 个 P1 self-noted:
- **P1-NEW1**: `_BUILTIN_DIR` 在 `prompt_registry.py` 中是 `prompts._BUILTIN_DIR` 的复制引用。Monkeypatch `prompts._BUILTIN_DIR` 时必须同步 patch `prompt_registry._BUILTIN_DIR`。当前测试已覆盖（`test_registry_builtin_dir_matches_prompts_module` + `test_summarizer_falls_back_when_template_missing` 双重 patch），但 production 代码若有第三方 monkeypatch 不会生效。**降级为 P2 风险**（不影响正常路径）。

---

## ⚠️ CRITICAL: Working Tree 污染（来自之前未提交 session）

`git status` 显示 working tree 有 **12 modified + 5 untracked** 文件，**非本 C1 commit 改动**：

| 类型 | 文件 |
|:--|:--|
| Modified (非本次) | `.gitignore`, `Dockerfile`, `docker-compose.yml`, `cli.py`, `config.py`, `source_aggregator.py`, `mcp_server.py`, `remix/__init__.py`, `test_cli.py`, `test_mcp_handlers.py` |
| Untracked (非本次) | `docs/subagent-security-template.md`, `remix/roles.py` |

**本 C1 真实改动**（仅这 4 个文件）:
- `src/builderpulse/remix/prompt_registry.py` (NEW)
- `src/builderpulse/core/pipeline.py` (modified)
- `tests/test_prompt_registry.py` (NEW)
- `tests/test_pipeline_remix.py` (modified)

**严重度**: P0 阻塞（commit 前必须 user 拍板）

**H44 R3 self-disclosure**: 不写 PASS。暴露问题等 user 决策。

---

## 🔍 R0 二次审查：污染文件全部出自 Session 31 "LightRAG 角色抽象"

读 4 个关键文件后发现：

| 文件 | Session 31 内容（摘要） |
|:--|:--|
| `remix/roles.py` (NEW) | `Role` enum (EXTRACT/QUERY/KEYWORDS/TRANSLATE) + `RoleSpec` + `RoleLLMRegistry`，**派生 from LightRAG llm_roles.py** |
| `remix/__init__.py` | export `Role`, `RoleLLMRegistry`, `RoleSpec`, `get_role_provider` |
| `core/config.py` | 加 `role_llm_model_map` + `role_llm_registry` property |
| `cli.py` (+36) | 加 `--role-model` CLI flag 调用 `role_llm_registry` |
| `source_aggregator.py` (+168) | 重大重构 — 大概率 `fetch_all_sources` 多 source 编排 |
| `mcp_server.py` (+16) | MCP handler 走 role provider |

**关键观察**：
- Session 31 是 **C1 的逻辑前置**（C1 改 step_summarize 调用 `Role.EXTRACT`，正是依赖 roles.py 这个未追踪文件）
- 如果只 commit C1 不 commit Session 31 → fresh clone 会因 `from builderpulse.remix.roles import` 失败
- 但 Session 31 也没 commit → working tree 是"半成品"状态

## 判定

**⚠️ BLOCK on user decision**（不进 R1a，需 user 拍板 commit 策略）

候选 3 路径：
- A. **Session 31 先单独 commit**（可能需要拆 1-2 个 commit：roles + config/cli/aggregator）→ 再 C1 commit
- B. **C1 + Session 31 一起 commit**（违反 "单一关注点" 原则，但逻辑紧耦合）
- C. **C1 暂不 commit**，先 Review Session 31 走完 5 轮，再 C1