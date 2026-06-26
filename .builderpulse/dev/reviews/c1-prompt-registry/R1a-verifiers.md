# R1a — 3 Verifier 交叉验证报告 (v2.2.0 Commit 1)

> **范围**: v2.2.0 Commit 1 (RolePromptRegistry + step_summarize 接入)
> **方法**: 3 independent subagent 并行验证 (互不通信)
> **H45 item 13**: 不写 PASS verdict

## Verifier 矩阵

| Verifier | 焦点 | 严重度 | 一句话 |
|:--|:--|:--|:--|
| **V1** (测试覆盖) | 单测覆盖度 / mock | 0 P0 / 0 P1 / 6 P2 | 16/16 pass + 1:1.89 测试比例；`test_warm_caches_all_roles` 命名误导 |
| **V2** (集成正确性) | 调用链 / fallback / 一致性 | 0 P0 / 0 P1 / 1 P2 | `Config.prompts_dir` 不存在 → production `custom_dir` 链不可达 |
| **V3** (生产就绪度) | 文档 / API surface / 配置 | **1 P0** / 3 P1 / 4 P2 | `RolePromptRegistry` 未在 `__init__.py` export (P0)；`Config.prompts_dir` 缺失 (P1) |

**3/3 共识**：
- **1 P0** (V3): `__init__.py` export 缺失
- **1 共享 P1** (V2 + V3): `Config.prompts_dir` 字段缺失
- **P2-1** (V1): 测试命名误导（不阻塞）

## P0 阻塞（必修）

### P0-A1: `RolePromptRegistry` 未在 `remix/__init__.py` export (V3)

**位置**: `src/builderpulse/remix/__init__.py`

**现象**: `remix/__init__.py` 当前导出 `Role` / `RoleLLMRegistry` / `RoleSpec` / `get_role_provider` (Session 31 加) + `Summarizer` / `Translator` / `get_provider`，但**没** `RolePromptRegistry`。

**影响**: 第三方 plugin / 用户代码写 `from builderpulse.remix import RolePromptRegistry` 失败 → Public API surface 一致性破坏。

**修复**（V3 给出）: 加 1 行 `from .prompt_registry import RolePromptRegistry` + `__all__` 加 1 行。

**修复成本**: 2 行

---

## P1 高优（user 拍板）

### P1-C1: `Config` 缺 `prompts_dir` 字段 (V2 + V3 共享)

**位置**: `src/builderpulse/core/config.py:65-117` (Config dataclass 15 字段列表)

**现象**:
- `pipeline.py:148` 用 `getattr(ctx.config, "prompts_dir", None)` 兜底
- 真实 `Config()` 实例永远没有 `prompts_dir` 属性 → `getattr` 永远返回 `None`
- **production `custom_dir` 链不可达**（只能走 builtin + default fallback）
- 用户**无法**通过 `bp config set prompts_dir=...` 或 `BUILDERPULSE_PROMPTS_DIR` env var 自定义 prompt 目录

**V2 实证**:
```
getattr(config, "prompts_dir", None) → None (always)
3-tier 优先级 (custom > builtin > default) 实际只有 (builtin > default-fallback) 在 production 真正工作
```

**3 选项（V2 + V3 共同给出）**:
- **A**（最小变更）: 文档明示 builtin-only，custom 留 v2.3.0 plugin entry_points
- **B**（治本）: 加 `Config.prompts_dir: str | None = None` 字段 + CLI flag + env var 支持
- **C**（接受现状）: 不动，仅 R3 residual 标记

**修复成本**: A=0 行（仅 docs） / B=~10 行（Config 字段 + CLI flag + env var） / C=0 行

### P1-DP1: PEP 604 union syntax vs `requires-python = ">=3.9"` (V3)

**位置**: `src/builderpulse/remix/prompt_registry.py` 多处 `Path | None`

**现象**: PEP 604 union syntax (`X | None`) Python 3.10+ 运行时支持。`<3.10` 需要 `from __future__ import annotations` 兜底（已加 ✓）。

**影响**: 0（future import 已修）

**处理**: 已 done，文档化即可。

### P1-D1: `get()` docstring 缺 custom_dir priority 说明 (V3)

**位置**: `src/builderpulse/remix/prompt_registry.py:get()` docstring

**现象**: 4-tier 优先级仅在模块 docstring，方法 docstring 缺失。

**修复**: 1 段落补全 docstring。

**修复成本**: 3-5 行

---

## P2 列表（合并 3 verifier, 9 项）

| ID | 来源 | 描述 |
|:--|:--|:--|
| P2-1 | V1 | `test_warm_caches_all_roles` 命名误导（实际不调 `warm()`） |
| P2-2 | V1 | `get()` cache 命中早退路径无测试 |
| P2-3 | V1 | `warm()` 容错分支无断言 |
| P2-4 | V1 | fallback to `<role>-default.md` 路径未实测（builtin 当前无 default 文件） |
| P2-5 | V1 | step_summarize 3 edge 未覆盖（`prompts_dir=""` / `"/nonexistent"` / `source_type=""`） |
| P2-6 | V1 | R0 P1-NEW1（已降级 P2） |
| P2-7 | V3 | 空文件静默接受 |
| P2-8 | V3 | `__init__` 缺 docstring |
| P2-9 | V3 | 缺 init log |

**P2 处理**: 全部 backlog（仅 P2-1 建议 commit 前快速修，因测试命名误导会让未来 debug 困惑）

## P3 列表（合并 3 verifier, 13 项）

V1 (4): test naming consistency / cache mutation safety / warm 容错 silent / fallback 错误信息
V2 (7): signature fragile / 死代码 / cache staleness / Path 静默丢 / 一致性副作用 / Mock fragile / R0 stale
V3 (6): `_BUILTIN_DIR` 双重 monkeypatch / 性能 / `_cache` 非线程安全 / 其他 minor

**P3 处理**: 全部 backlog

## OK 列表（合并 3 verifier 共识）

- ✅ 16/16 C1 测试 pass（6 test_prompt_registry + 10 test_pipeline_remix）
- ✅ 609 regression pass + 4 skip
- ✅ 1:1.89 代码:测试比例（远超 1:0.8 阈值）
- ✅ 所有新函数 CC ≤ 6（< 10 阈值）
- ✅ 0 新依赖
- ✅ 0 Public API 破坏（除 P0-A1 export 缺失）
- ✅ `step_summarize` graceful degradation（模板缺失 → 空 system 保留 v2.1.0 行为）
- ✅ `prompts_dir` 不存在时 monkeypatch-friendly（getattr 兜底）
- ✅ `_BUILTIN_DIR` 与 `prompts._BUILTIN_DIR` 同步（测试覆盖）
- ✅ `__future__ import annotations` 兜底 PEP 604 union syntax
- ✅ 模块 docstring 完整

## 3/3 共识判定

**修 P0-A1（2 行）+ user 拍板 P1-C1 → 进 R1b（对抗性）**。

P2 / P3 全部 backlog，不阻塞 commit。

## 已采取行动（写本报告时同步修）

- [x] **P0-A1**: 加 `RolePromptRegistry` 到 `remix/__init__.py` export（已修 + 实证 `from builderpulse.remix import RolePromptRegistry` OK）
- [x] **P1-C1**: user 拍板 **B 治本** → 已加 `Config.prompts_dir: Optional[str] = None` 字段（config.py:81-87）
  - env var `BUILDERPULSE_PROMPTS_DIR` 自动支持（via `_apply_env_overrides`）
  - `from_file()` / `from_defaults()` / 直接构造 / to_dict 全路径覆盖
  - pipeline.py 去掉 `getattr` fallback，直接 `ctx.config.prompts_dir`
  - 加 3 个测试 (test_config_has_prompts_dir_field / test_config_prompts_dir_env_override / test_config_prompts_dir_round_trip)
- [x] P1-DP1: 已 done（future import）
- [ ] P1-D1: 加 get() docstring custom_dir priority 段（**已 done 跟 P1-C1 同步** — 字段说明加在 get() docstring 中，描述 4-tier 优先级）

## 决策树

```
P0-A1 (必修) ─┐
              ├─→ 修完 → R1b 对抗
P1-C1 (拍板) ┘   ↑
                  └─ A: builtin-only docs, P1-D1 doc 改 "builtin-only mode"
                    B: 加 Config 字段 + CLI flag + env var, P1-D1 doc 完整
                    C: 不动, P1-D1 doc 加 "by design" 注
```