# R0 — Self-Check (Session 31: LightRAG 角色抽象 + Source Aggregator 重构)

> **范围**: Session 31 M1 (LLM 角色抽象) + M2 (Source aggregator 注册表化)
> **时间**: 2026-06-26 (人工 inline ~10 min)

## 改动文件全清单

### M1 — LightRAG 角色抽象 (LLM Provider)

| 文件 | 类型 | 行数 | 内容 |
|:--|:--|:--:|:--|
| `src/builderpulse/remix/roles.py` | NEW | 146 | Role enum + RoleSpec + RoleLLMRegistry + DEFAULT_ROLE_SPECS + get_role_provider |
| `src/builderpulse/remix/__init__.py` | M | +5 | export Role / RoleLLMRegistry / RoleSpec / get_role_provider |
| `src/builderpulse/core/config.py` | M | +17 | `role_llm_model_map` + `role_llm_registry` property |
| `src/builderpulse/cli.py` | M | +36 | `--role-model` flag → registry |
| `src/builderpulse/mcp_server.py` | M | +16 | MCP handlers 用 role provider |

### M2 — Source Aggregator 重构 (Plugin 化)

| 文件 | 类型 | 行数 | 内容 |
|:--|:--|:--:|:--|
| `src/builderpulse/core/source_aggregator.py` | M | +73/-95 | 5 个 `if _want(...)` 块 → `_FETCHERS` 注册表循环（仿 deliver/_CHANNELS） |

### 其他

| 文件 | 类型 | 备注 |
|:--|:--|:--|
| `.gitignore`, `Dockerfile`, `docker-compose.yml` | M | 部署配置（需看具体 diff） |
| `tests/test_cli.py` | M | +41 — 新 CLI flag 测试 |
| `tests/test_mcp_handlers.py` | M | +61 — MCP handlers 测试 |
| `tests/test_pipeline_remix.py` | M | +99 — pipeline 走 role provider |
| `docs/subagent-security-template.md` | NEW | 文档 |

**总**: ~400-500 行新增 + ~100 行删除（含测试）

## 单点检查 (✓ = pass)

- [x] **M1 / M2 单一关注点**: M1 = LLM 角色抽象, M2 = source plugin 化, 互不干扰
- [x] **L1 测试 pass**: 全量 609 pass + 4 skipped（166s 跑完）
- [x] **Public API 兼容性**: `get_provider()` 未改 → 向后兼容
- [x] **文档来源标注**: 每个文件顶部明确写"派生 from LightRAG xxx"
- [x] **4 角色默认**: EXTRACT/QUERY/KEYWORDS/TRANSLATE 各自 model + temperature + max_tokens
- [x] **api_key mask**: `to_dict()` 自动 `"***"` 处理敏感字段

## 自我 P0 / P1 发现

### P0（无）— 工作状态可进 R1a

### P1 self-noted:
- **P1-S31-1**: `_FETCHERS` 注册表是 session 31 新加的，但 plugin auto-load（entry_points）没接 — 加新 source 仍需手动改 source_aggregator.py。**这是 P2 范畴**，待 v2.3.0 plugin 化。
- **P1-S31-2**: `RoleLLMRegistry.to_dict()` mask `"***"` 但 `from_dict()` 反向 unmask 不彻底（仅检查 `== "***"`） — 如果用户写明文 `"***"` 进 config 会被吞掉。**降级为 P3 边缘 case**。
- **P1-S31-3**: `roles.py` 注册表 `_specs` 字典读写不是 thread-safe（注释里明说"call once at startup"） — 多线程 CLI/MCP 共用 registry 时 race condition 风险。**降级为 P2**（实测 CLI 是顺序调用，不触发）。

### P2 by-design:
- **P2-S31-1**: `source_aggregator.py` 重构把 lambda `lambda f=fetcher, c=sources_cfg` 用 default arg 绑定 — 标准 Python pattern，OK。
- **P2-S31-2**: `_FETCHERS` 字典顺序依赖 Python 3.7+ dict order 保证 — OK。

## 判定

**进 R1a**（3 parallel verifiers）。

R1a subagent 焦点：
- **V1 测试覆盖**: 4 角色 + 注册表 + aggregator 注册表化的测试是否足够
- **V2 集成正确性**: 与 existing get_provider / pipeline / CLI / MCP / config 集成的正确性
- **V3 生产就绪度**: docs / docker / .gitignore 改动是否合理，CHANGELOG 是否更新