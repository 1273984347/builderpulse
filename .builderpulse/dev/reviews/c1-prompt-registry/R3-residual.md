# R3 — Residual Risk 确认 (v2.2.0 Commit 1)

> **审查人**: 主代理 inline (per H44)
> **审查对象**: v2.2.0 Commit 1 (RolePromptRegistry) + R1a + R1b + R2 闭环后
> **H45 item 13**: 0 finding 必写 N residual risk，不写 PASS verdict

## P0 阻塞：0 项

| 修复 | 来源 | 状态 |
|:--|:--|:--|
| RolePromptRegistry export | R1a V3 P0-A1 | ✓ |
| Config.prompts_dir 字段缺失 | R1a V2+V3 P1-C1 | ✓ (选项 B 治本) |
| TARGET_CONFIG_VERSION 不一致 | R1b A1 | ✓ (1 行 bump) |
| pipeline.py getattr fallback regression | R1b A3 | ✓ (恢复 getattr) |
| to_dict env-override 污染 | R1b A4 | ✓ (新参数 + _env_overridden 跟踪) |

**5 项 P0/P1 全部修复，REPL 实证成立。**

## P1 高优：0 项新增 + 1 项遗留（deferred）

### P1-RR-1 [遗留 from R1a P0-C]: S31 22 个新 Public API 0 直接单测

- **触发条件**: 任何 Session 31 新代码路径重构
- **范围**: roles.py 11 API + source_aggregator.py 11 API
- **当前缓解**: 616 间接集成测试 pass (CLI/MCP/pipeline)
- **治本方案**: S31 owner 决定 deferred 到下个 session
- **状态**: CHANGELOG v2.2.0 S2 line 75-83 已 explicit 标注 by-design

## P2 中优：3 项

### P2-RR-1: `_apply_env_overrides` CC=10 触阈

- **位置**: `src/builderpulse/core/config.py:199-235`
- **触发条件**: 该函数天然多分支（env 解析 + type 推断 + Optional 处理 + 异常回退）
- **缓解**: 拆 `_parse_env_value(fld_type, env_val)` helper 降 CC（v2.2.x 优化）

### P2-RR-2: `step_summarize` CC ~14 (R1b A3 后)

- **位置**: `src/builderpulse/core/pipeline.py:117-194`
- **触发条件**: 该函数需处理多个分支（role registry + prompts registry + LLM 调用 + fallback）
- **缓解**: 拆 helper（v2.2.x 重构）

### P2-RR-3: `RolePromptRegistry._BUILTIN_DIR` 是 re-export 引用

- **位置**: `src/builderpulse/remix/prompt_registry.py:33`
- **触发条件**: 第三方代码 runtime 改 `prompts._BUILTIN_DIR` 不会 pick up
- **缓解**: 文档化 by-design (R0 self-check P1-NEW1 已降级 P2)

## P3 低优 / by-design：3 项

### P3-RR-1 [by-design]: `to_dict(include_env_overrides=True)` 仍 mask api_key

- **设计**: `mask_secrets=True` 优先级高于 `include_env_overrides`，正确设计
- **无需修**

### P3-RR-2 [cosmetic]: CHANGELOG 双段 `[2.2.0]`

- **位置**: CHANGELOG.md line 8 (S1) + line 8 (S2, 我加的)
- **现象**: 同版本号两段（S1 在前，S2 在后）
- **缓解**: v2.3.0 时合并或加 `[2.2.0-S1]` / `[2.2.0-S2]` 子段

### P3-RR-3 [backlog]: R1a R1a V1 P2-1 (test_warm_caches_all_roles 命名误导)

- **位置**: `tests/test_prompt_registry.py:90-105`
- **现象**: 测试名"warm caches all roles"但实际不调 `warm()`
- **缓解**: v2.2.x 测试清理时统一重命名

---

## Residual 综合判定

**survive** — 0 P0 + 0 P1 新增 + 3 P2 backlog + 3 P3/by-design

按 H45 item 13 规则，C1 commit 闭环条件满足。

---

## C1 commit DoD (per plan)

| DoD 项 | 状态 |
|:--|:--|
| 5 轮 review 全过 (R0/R1a/R1b/R2/R3) | ✓ |
| 5 文件齐全 (R0-self-check.md / R1a-verifiers.md / R1b-adversarial.md / R2-audit.md / R3-residual.md) | ✓ |
| P0-A1 export 修复 | ✓ |
| P1-C1 治本 (选项 B: Config 字段 + env var) | ✓ |
| R1b A1/A3/A4 修复 | ✓ |
| 5 修复 REPL 实证 | ✓ |
| pytest 616 pass + 4 skip (0 fail) | ✓ |
| CHANGELOG v2.2.0 S2 段 (含 C1) | ✓ |
| 版本号对齐 (2.2.0) | ✓ |
| R3 残余风险列表写完 | ✓ (本文件) |

**C1 review 闭环 ✓ 可进 commit**

---

## 5 轮 review 文件清单

```
.builderpulse/dev/reviews/c1-prompt-registry/
├── R0-self-check.md       (主代理 inline, 5 min)
├── R1a-verifiers.md       (3 parallel subagent: V1 测试 / V2 集成 / V3 生产)
├── R1b-adversarial.md     (1 adversarial subagent, 找到 3 P1)
├── R2-audit.md            (1 independent subagent, 44/45)
└── R3-residual.md         (本文件, 主代理 inline)
```