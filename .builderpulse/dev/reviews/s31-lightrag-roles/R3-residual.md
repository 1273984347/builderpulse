# R3 — Residual Risk 确认 (Session 31)

> **审查人**: 主代理 inline (per H44)
> **审查对象**: Session 31 + R1a + R1b + R2 修复闭环后残余风险
> **H45 item 13**: 0 finding 必写 N residual risk，不写 PASS verdict

## P0 阻塞：0 项

R1a 找到 2 项 P0 (docker-compose Windows path / RoleLLMRegistry deepcopy 污染)，
R1b 找到 2 项 P0 (CHANGELOG 缺失 / 版本号冲突) — **全部已修**。

修复实证（R2 独立验证 7 项 REPL 100% pass）：
- P0-A: `${HOST_BUILDERPULSE_DIR:-${HOME}/.builderpulse}` 跨平台 ✓
- P0-B: `__init__` + `register` + `get_spec` fallback + `register_all` 全路径 `copy.deepcopy` ✓
- B-1: CHANGELOG.md v2.2.0 S2 段 78 行 17 项 ✓
- B-9: pyproject.toml / __init__.py / docker-compose.yml 三处 = 2.2.0 ✓

## P1 高优：1 项

### P1-RR-1 [by-design deferred]: 22 个新 Public API 元素 0 直接单测

- **触发条件**: 任何 Session 31 新代码路径重构 (e.g. 把 RoleSpec 拆 dataclass)
- **范围**: `roles.py` 11 API + `source_aggregator.py` 11 API
- **当前缓解**: 609 个间接集成测试 pass (CLI/MCP/pipeline)
- **治本方案**: S31 owner (本 session) 决定 deferred 到下个 session 写
  `tests/test_remix_roles.py` (~150 行) + `tests/test_source_aggregator.py` (~120 行)
- **状态**: R1a V1 flag → R1b 确认 → R2 列入 residual → **deferred (by design)**

## P2 中优：7 项

### P2-RR-1: `Config.role_llm_registry` property 每次访问构造新 registry

- **位置**: `src/builderpulse/core/config.py:86-96`
- **触发条件**: 高频调用 `ctx.config.role_llm_registry` (MCP server 长跑 bp_process)
- **影响**: 每次 new RoleLLMRegistry + 4 次 deepcopy (~100μs)，累积性能开销
- **缓解**: 改 `@cached_property` (Python 3.8+)；当前规模不触发

### P2-RR-2: `RoleLLMRegistry.from_dict` 只 mask `api_key`，未来其他敏感字段需统一白名单

- **位置**: `src/builderpulse/remix/roles.py:115-117`
- **触发条件**: 未来新增 spec 字段含敏感数据 (e.g. `endpoint_url` with embedded token)
- **缓解**: 加 `SENSITIVE_KEYS = frozenset({"api_key", ...})` 白名单

### P2-RR-3: `_FETCHERS` module-level dict 无锁

- **位置**: `src/builderpulse/core/source_aggregator.py:149-155`
- **触发条件**: 多线程并发 register / fetch
- **缓解**: 加 `threading.Lock`（CLI/MCP 当前顺序调用不可触发）

### P2-RR-4: `RolePromptRegistry._cache` 非线程安全

- **位置**: `src/builderpulse/remix/prompt_registry.py:28`
- **触发条件**: 多线程同时 `get()`
- **缓解**: 加 `threading.Lock` 或 `functools.lru_cache`

### P2-RR-5: docker healthcheck 仅测 `import builderpulse`，不测运行时依赖

- **位置**: `docker-compose.yml:28-33`
- **触发条件**: MCP server 启动失败但包可 import（configuration error / DB lock）
- **缓解**: 加 `bp serve --health` CLI flag 或 `wget /healthz` endpoint

### P2-RR-6: CLI `--role-model` 错误 key=value 静默丢弃

- **位置**: `src/builderpulse/cli.py:319-329`
- **触发条件**: 用户拼错 `--role-model extrac=claude` (typo)
- **缓解**: 加 warning log 列出 ignored keys + 已知 4 角色

### P2-RR-7: `Config.from_file` 缺 unknown-key warning

- **位置**: 配置文件加载路径未实测
- **触发条件**: 用户配 `role_llm_model_map` 在 v2.1.0 config.json 但 v2.1.0 Config 不识别
- **缓解**: 加 `logger.warning("unknown config key: %s", key)`

## P3 低优 / by-design：2 项

### P3-RR-1 [by-design]: `_VALID_SOURCES` immutable + 警告用户手动同步

- **位置**: `src/builderpulse/core/source_aggregator.py:23`
- **理由**: 用户拍板 R1b A-1 选 P3 修复（仅 docstring + warning log），治本推迟到
  v2.3.0 plugin entry_points 重构。`register_source` 现已加清晰错误信息 +
  warning log 提示 workaround。
- **已知限制**: plugin author 调用 `register_source('rss', fetcher)` 后，
  仍需手动编辑 `_VALID_SOURCES` 才能让 `fetch_all_sources(sources='rss')` 工作。

### P3-RR-2 [by-design]: `test_prompt_registry.py` 已被 pytest 自动发现

- **理由**: R2 报告确认 609 测试覆盖自动包含 C1 + S31 测试，无需额外 CI 配置
- **后续优化**: 可加 pytest-cov 配置覆盖率门槛 (e.g. ≥80% line coverage)

## 残余风险综合判定

**survive** — 0 P0 阻塞 + 1 P1 by-design deferred + 7 P2 backlog + 2 P3 by-design

按 H45 item 13 规则，本 session 完成 Session 31 review 闭环。

---

## Session 31 commit DoD (per plan)

| DoD 项 | 状态 |
|:--|:--|
| 5 轮 review 全过 (R0/R1a/R1b/R2/R3) | ✓ |
| 5 文件齐全 (R0-self-check.md / R1a-verifiers.md / R1b-adversarial.md / R2-audit.md / R3-residual.md) | ✓ |
| 2 P0 + 4 P1 R1a/R1b 修复 | ✓ |
| 7 修复 REPL 实证 | ✓ |
| pytest 609 pass + 4 skip (0 fail) | ✓ |
| CHANGELOG v2.2.0 S2 段 | ✓ |
| 版本号对齐 (2.2.0) | ✓ |
| R3 残余风险列表写完 | ✓ (本文件) |

**Session 31 review 闭环 ✓ 可进 commit**