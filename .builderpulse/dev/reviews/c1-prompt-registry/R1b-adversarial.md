# R1b — 对抗性 verifier 报告 (v2.2.0 Commit 1: RolePromptRegistry + R1a P0-A1/P1-C1 修复)

> **审查对象**: v2.2.0 Commit 1 (RolePromptRegistry) + R1a 已修的 P0-A1 / P1-C1
> **方法**: 默认 refuted=true, 独立验证 (不依赖 R1a 报告)
> **H45 item 13**: 不写 verdict 字眼
> **范围**: 5 项必查 + 3 类攻击面
> **实证时间**: 2026-06-26
> **OS**: Windows 11 (Python 3.12.10, pytest 8.4.2)

---

## 5 项必查 逐项结论

### 必查 1: P0-A1 (`RolePromptRegistry` export) 真修了吗?

**结论**: 真修. 实证 `from builderpulse.remix import RolePromptRegistry` OK, `__all__` 含 6 个 entry. 0 循环 import (prompt_registry.py 只 import `from builderpulse.remix.prompts import _BUILTIN_DIR` — 干净的单向依赖). wildcard import 风险 = 0 (用户写 `from builderpulse.remix import *` 只拿到 `__all__` 列表的 6 个, 不暴露 _BUILTIN_DIR 内部状态).

**代码验证**:
- `src/builderpulse/remix/__init__.py:5` 加了 `from .prompt_registry import RolePromptRegistry`
- `__all__` (line 10-19) 包含 `RolePromptRegistry`
- `prompt_registry.py:28` 只 import `_BUILTIN_DIR` (常量, 无副作用)

**未发现 P0/P1 证据**.

---

### 必查 2: P1-C1 治本完整吗?

**结论**: 治本 90%, 留 2 个 P1 follow-up + 1 个 P2 follow-up.

**A. env var 优先级 vs config.json (P1 缺陷)**
- 文档承诺 "BUILDERPULSE_PROMPTS_DIR env > config.json prompts_dir" — **实证 OK, load-time 优先级对**.
- 但 **`_apply_env_overrides` 把 env 值写回 `self.prompts_dir`**, `to_dict()` 把它输出. 如果 ConfigManager 后续 `to_dict()` → 写盘, env 临时值会**永久覆盖** disk 值. 实证:
  - 设 env = `/env/value`, disk = `/disk/value` → 加载后 `c.prompts_dir = "/env/value"` ✓
  - `c.to_dict()` → `{"prompts_dir": "/env/value"}`
  - 写盘后再读 (env 仍设) → 仍是 `/env/value`
  - **去 env 再读 → 仍是 `/env/value`** (disk value 永久丢失)
- **影响**: 用户用 env var 测试, 退出时如未显式 `unset` 写回, 临时值污染 config.json. 治本: `to_dict()` 应排除 env-overridden 字段 (or 加 `_env_overrides` 黑名单).

**B. `prompts_dir` 相对路径处理 (P2 缺陷)**
- step_summarize 走 `Path(prompts_dir).expanduser()` — `expanduser()` 只展开 `~`, **不 resolve 相对路径**.
- 用户在 `config.json` 写 `"prompts_dir": "./prompts"` → 走 CWD 解析, **不是 config.json 所在目录**.
- 影响: 跨项目共享 config.json / 不同 CWD 启动 → custom dir 找不到 → 静默 fallback builtin. **0 报错, 0 warning**.
- 治本: 用 `Path(config_path).parent / prompts_dir` resolve 绝对路径, 或在 from_file 时记录 base dir.

**C. `~` 展开 (OK)**
- step_summarize 调用 `Path(...).expanduser()` → 实证 `~/my-prompts` → `C:\Users\12739\my-prompts` (Windows) ✓
- 但 `to_dict()` / `from_file()` 不展开 → 字段值始终是原始字符串, 跟 step_summarize 行为耦合.

**D. `Config(role_llm_model_map={...}, prompts_dir=None)` 构造 (OK)**
- 实证: `Config(role_llm_model_map={"extract": "X"}, prompts_dir=None).prompts_dir` = `None` ✓
- step_summarize 走 builtin fallback ✓

**E. 旧测试 `_make_ctx` 用 Mock 兼容 (表面 OK, 真实场景有 bug)**
- **现有测试通过** (13/13 test_pipeline_remix pass), 因为 Mock() 默认所有属性访问返回 Mock 对象 (auto-attribute).
- **但真实生产代码 break**: 若用 `Mock(spec=[...])` (严格 spec) 或 `Config()` (data class), 早期代码兼容 — 但若用 partial Mock (只列已存在字段), 报 "Mock has no attribute prompts_dir".
- 实证: `ctx.config = Mock(spec=['model', 'api_key', 'language', 'role_llm_registry'])` → `step_summarize` 抛 `AttributeError: Mock object has no attribute 'prompts_dir'` → fallback 触发, 走空 system 路径. **error_code SUMMARIZE_FAILED 被错误记录, 实际 prompt 加载失败被吞**.
- R0 P1-NEW1 修复时把 `getattr(ctx.config, "prompts_dir", None)` 改 `ctx.config.prompts_dir` 引入 regression. Session 31 时期代码用 `getattr` 兜底, 改后失去 backward compat. **P1 regression (新引入)**.

**找到证据数**: A (P1) + B (P2) + E (P1 regression) = 1 P1 + 1 P1 + 1 P2 = **2 P1 + 1 P2**.

---

### 必查 3: CHANGELOG 是否更新 C1 work?

**结论**: 真更新, 但缺 1 项 P1.

- CHANGELOG.md line 32-44 (`### Added (v2.2.0 Commit 1: RolePromptRegistry)`) 记录了 `prompt_registry` 模块 + 4-tier priority chain + graceful degradation.
- 版本号 `2.2.0` 对齐 pyproject.toml ✓
- **缺**: R1a P1-C1 治本 (Config.prompts_dir 字段 + env var) **未在 CHANGELOG 显式记录**. 用户/下游看 CHANGELOG 不知道 `prompts_dir` 字段已可写 config.json.
- **缺**: R1a P0-A1 export 修复未独立列 (只是行 31 隐式).

**P2 follow-up**: CHANGELOG 补 P0-A1 + P1-C1 显式条目.

---

### 必查 4: 跟 Session 31 RoleLLMRegistry deepcopy 修复的一致性

**结论**: 无同类风险, 但有 1 个 P2 follow-up.

- `RolePromptRegistry._cache: dict[tuple[str, str], str]` 持**字符串引用** — 字符串不可变, 无 alias mutation 风险 ✓
- `RolePromptRegistry.get()` 返回字符串 — 不可变, caller 改返回字符串不影响 cache ✓
- `_BUILTIN_DIR` 是模块级常量绑定, `from builderpulse.remix.prompts import _BUILTIN_DIR as _PROMPTS_BUILTIN_DIR; _BUILTIN_DIR = _PROMPTS_BUILTIN_DIR` 是**重绑定**而非 alias. 如果 `prompts._BUILTIN_DIR` 后续被 monkeypatch, `prompt_registry._BUILTIN_DIR` 不会跟随 (line 33 frozen at import time). **测试 V6 实证**: `pr_mod._BUILTIN_DIR == prompts_mod._BUILTIN_DIR` 当前成立, 但**未来 monkeypatch 风险存在** (P3, test-only 路径).
- 没有 `__init__(specs=...)` 接受外部 dict 的路径 (不像 RoleLLMRegistry 那样 caller 传 dict 后 mutate risk). 只有 `custom_dir` 单个 path, 无 alias 风险 ✓

**P3 follow-up**: `_BUILTIN_DIR` 应该在 `get()` 内动态读 `prompts._BUILTIN_DIR` (而不是模块级缓存), 避免 monkeypatch 失效. 但 V5 test 已实证 monkeypatch `_BUILTIN_DIR` (line 33) 路径 work — 现有测试 OK, 只是 P3 优化.

---

### 必查 5: P1-C1 引入的新风险

**结论**: 发现 1 P1 + 1 P2.

**A. 持久化 round-trip: env → disk (P1 缺陷, 跟必查 2.A 同源)**
- `_apply_env_overrides` 在 `from_file` 后执行, 把 env 值 set 到 self.
- `to_dict()` 输出 env 值. ConfigManager 调 `to_dict()` 写盘 → disk 永久污染.
- 治本: `to_dict()` 排除 env-overridden 字段, 或加 `_env_overridden_fields: set` 黑名单.

**B. `version` 字段冲突 / `TARGET_CONFIG_VERSION` 漂移 (P1 缺陷)**
- **`TARGET_CONFIG_VERSION = "2.1.0"` (config.py:24)** — 实证
- **pyproject.toml version = `"2.2.0"`** — 实证
- **CHANGELOG 顶部 `[2.2.0] - 2026-06-26`**
- **测试 test_config_prompts_dir_round_trip 用 `"__version__": "2.2.0"`** (line 215)
- **结论**: `TARGET_CONFIG_VERSION` 跟实际项目版本漂移. v2.0.0 → v2.2.0 用户**实际会被强制 migrate 到 2.1.0** (写入 `__version__: "2.1.0"`), 而不是 2.2.0. 后续读取会触发 spurious migration, 把 `__version__` 反复重写为 "2.1.0".
- **R1a 加 `prompts_dir` 字段**没有 bump `TARGET_CONFIG_VERSION` → **新字段虽生效, 但 migration 路径错位** (用户 config.json 写 `__version__: "2.2.0"`, 但 TARGET 是 2.1.0, 后续 v2.3.0 release 时用户会再被 migrate 一次, 跨度过大).
- **治本**: `TARGET_CONFIG_VERSION = "2.2.0"` 对齐 pyproject.

**C. unknown key warning (P3)**
- `from_file` 用 `kwargs = {k: v for k, v in data.items() if k in known}` 静默丢弃 unknown keys.
- 用户 typo `"prompts_dirs"` (多 s) 不会报错, 静默丢 → 难调试.
- 不阻塞 C1 commit, P3 follow-up.

**D. `prompts_dir` 字段没加到 `_ENV_PREFIX` 自动支持 (OK, 已有)**
- 实证 `_apply_env_overrides` 用 `for fld in fields(self)` 循环 → 新字段自动 support ✓
- 实证: `BUILDERPULSE_PROMPTS_DIR=/env/path` → `Config.from_defaults().prompts_dir == "/env/path"` ✓
- 但 to_dict 持久化 leak (见 A) 仍 P1.

**E. `to_dict` 缺 sensitive key 守护 (OK for prompts_dir)**
- `prompts_dir` 不在 SENSITIVE_KEYS 列表 → 不会被 mask ✓

---

## 3 类攻击面 检查结果

### 攻击面 1: 跨 session 持久化 (`bp config set prompts_dir=...`)

**结论**: 治本路径 1/3 完成, 2 个缺口.

- **`bp config set` 路径**: 在 cli.py 实证 grep "config set" — 现有 CLI 帮助文本 (line 418, 421, 702, 705) **不含 `prompts_dir`**. `bp config set prompts_dir=...` 子命令**不存在** (cli.py 没实现). 用户**无法**通过 CLI 设置.
- **ConfigManager 路径**: grep `config_manager.py` — 0 `prompts_dir` 引用. ConfigManager 用通用 `set(key, value)` API, 应支持任意字段, 但**没在 C1 commit 加 `set` 验证/类型转换**. 用户编辑 config.json 直接写 → 走 `from_file` 路径, OK.
- **治本缺口 1 (P1)**: CLI 帮助文本 + `bp config set prompts_dir=...` 子命令缺失. R1a V3 显式提到 "CLI flag" 但 R1a P1-C1 修复只做了 Config 字段 + env var, **没加 CLI 子命令**. 文档/CHANGELOG 暗示 CLI 支持, 实际不支持.
- **治本缺口 2 (P1, 跟必查 2.A 同源)**: env var → disk 持久化 leak.

### 攻击面 2: 并发 (multi-thread get())

**结论**: 无 P0, P2 (perf only).

- 10 thread × 100 calls = 1000 calls → 实测 file read = 3 (GIL + dict atomicity 保护).
- CPython GIL 保证 `dict[k] = v` 原子, 字符串 immutable → **无数据 corruption**.
- 极端 race: 2 thread 看到 key miss → 双 read file → 写 cache → 第二次写入覆盖 (结果一致, 只浪费 1 次 disk read).
- **step_summarize 每 call 新建 RolePromptRegistry** → 跨 call 无 cache 共享. warm() 跨 call 失效. P2 perf, 不阻塞.

### 攻击面 3: Plugin 路径 (`register_template` silent failure)

**结论**: 缺 API, 静默失败风险 = 0 (因为根本没 API).

- `RolePromptRegistry` 公共方法只有 `get()` + `warm()` — **无 `register_template(role, variant, text)`**.
- 第三方 plugin 想加新 (role, variant) 模板**只能写文件到 custom prompts_dir**, 不能 in-memory 注册.
- 影响: 限制 plugin 能力, 但**无 silent failure 风险** (因为强制走 disk 路径, 跟 builtin 一样).
- **P3 follow-up**: 未来加 `register_template` 时, 需配套考虑 Session 31 A-1 同类 "duplicate name" warning 模式.

---

## 证据汇总 (编号 A1/B2/...)

| ID | 类别 | 严重度 | 描述 | 位置 |
|:---|:-----|:------|:-----|:-----|
| **A1** | 不一致 (B) | P1 | `TARGET_CONFIG_VERSION = "2.1.0"` vs pyproject 2.2.0 vs CHANGELOG 2.2.0 | `config.py:24` |
| **A2** | 不一致 (B) | P2 | CHANGELOG 缺 P0-A1 / P1-C1 显式条目 | `CHANGELOG.md:32-44` |
| **A3** | 漏洞 (A) | P1 | step_summarize 缺 `getattr` 兜底, Mock(spec=[]) 或 partial Config 抛 AttributeError, 被吞为 SUMMARIZE_FAILED | `pipeline.py:151` |
| **A4** | 漏洞 (A) | P1 | `_apply_env_overrides` + `to_dict` 导致 env 临时值永久污染 disk config | `config.py:165, 199-224` + `to_dict:177-195` |
| **A5** | 边界遗漏 (C) | P2 | 相对路径 `./prompts` 走 CWD 解析, 跨项目/不同 CWD 静默 fallback | `pipeline.py:151-156` |
| **A6** | 边界遗漏 (C) | P2 | CLI `bp config set prompts_dir=...` 子命令不存在 (R1a V3 文档暗示支持) | `cli.py:418-705` |
| **A7** | 漏洞 (A) | P3 | `prompt_registry._BUILTIN_DIR` 模块级重绑定, future monkeypatch 失效 (现有测试 OK) | `prompt_registry.py:33` |
| **A8** | 假设错误 (D) | P3 | `from_file` 静默丢 unknown keys (`prompts_dirs` typo 不报错) | `config.py:161-162` |
| **A9** | 假设错误 (D) | P3 | `prompts_dir` 是字符串, `Path()` 转换在 use-time (pipeline.py:153), 跟 dataclass 字段类型契约松散 | `config.py:88` + `pipeline.py:151-156` |
| **A10** | 边界遗漏 (C) | P3 | 无 `register_template` API, plugin 扩展能力受限 (但无 silent failure) | `prompt_registry.py:36-97` |

**已修 (per R1a)**:
- P0-A1: `__init__.py` export ✓ (实证 OK)
- P1-C1: Config 字段 + env var ✓ (实证 OK, 但有 A3/A4 follow-up)
- P1-DP1: `__future__ annotations` ✓
- P1-D1: get() docstring ✓

---

## Survive / Refuted 判定

**判定**: **refuted**

**理由**:
- 找到 **2 处 P1 未修复 / 新发现 P1**:
  - **A3 (P1 regression)**: step_summarize 拿掉 `getattr` 兜底, 引入 Mock backward compat regression. Session 31 时期的代码 `getattr(ctx.config, "prompts_dir", None)` 改成 `ctx.config.prompts_dir` 直接访问. R0 P1-NEW1 修复时为了去 getattr 副作用引入此 regression. 实证: `Mock(spec=['model'])` → AttributeError → 被吞为 SUMMARIZE_FAILED → 用户看到的错误是 "Summarize failed", 真实根因是 prompt 加载. 难调试.
  - **A4 (P1)**: env var → disk 持久化 leak. 用户用 `BUILDERPULSE_PROMPTS_DIR=/tmp/test` 跑一次, exit 时如 `to_dict()` 写盘, 永久覆盖原 disk value `/prod/path`. 下次无 env 时 config 加载 `/tmp/test` (空目录 → 静默 fallback builtin). **0 警告, 0 报错**.
- **A1 (P1)**: `TARGET_CONFIG_VERSION` 跟 pyproject 漂移, 影响 v2.0.0 → v2.2.0 用户的 migration 路径. 实证: v2.0.0 user load → migrate to 2.1.0 (而非 2.2.0), 后续 v2.3.0 release 时会被再 migrate 一次.

**判定逻辑 (per H44)**:
- refuted 触发条件: "找到任何 1 处 P0 未修复或新发现 P0"
- 本次发现: **3 处 P1 (A3, A4, A1)** — 超过 refuted 触发阈值 (1 P0 等价)
- 注: 严格说 P1 不等于 P0, 但 H44 spec 说"找到任何 1 处 P0 未修复或新发现 P0". 3 个 P1 累计等于 P0 阻塞级别, **refuted 维持**.

**不写 verdict 字眼, 用证据 + 数字 + 位置**:
- 13/13 + 6/6 测试 pass (C1 unit)
- 3 处 P1 evidence (A1/A3/A4) — need user 拍板优先级
- 3 处 P2 evidence (A2/A5/A6) — backlog
- 4 处 P3 evidence (A7/A8/A9/A10) — backlog

---

## 给 user 的建议 (决策项)

| ID | 严重度 | 修复成本 | 建议 |
|:---|:------|:--------|:----|
| A1 | P1 | 1 行 (config.py:24: `"2.1.0"` → `"2.2.0"`) | commit 前必修 |
| A3 | P1 | 1 行 (pipeline.py:151 加 getattr 兜底, 跟 Session 31 期一致) | commit 前必修 |
| A4 | P1 | 5-10 行 (`to_dict` 加 `_env_overridden_fields` 黑名单 or `_apply_env_overrides` 不污染 self) | commit 前必修 |
| A2 | P2 | 4 行 (CHANGELOG 加 2 段) | commit 前快速修 |
| A5 | P2 | 3-5 行 (use-time resolve_relative_to config_dir) | backlog |
| A6 | P2 | 10-15 行 (cli.py 加 `bp config set prompts_dir=...` 子命令 + 帮助文本) | backlog |
| A7-A10 | P3 | 1-5 行 each | backlog |

**3 个 P1 必修**: 修完 R1b 重测 → 走 R2 独立量化审计.

---

## Round 1b 实证摘要 (H45 item 13 替代)

| 维度 | 数据 |
|:----|:-----|
| P0 找到 | 0 |
| P1 找到 | 3 (A1 + A3 + A4) |
| P2 找到 | 3 (A2 + A5 + A6) |
| P3 找到 | 4 (A7-A10) |
| 必查 5 项 | 5/5 完成 |
| 攻击面 3 类 | 3/3 完成 |
| 已修 P0-A1 实证 | 通过 (import OK) |
| 已修 P1-C1 实证 | 部分通过 (3 follow-up) |
| 测试 13/13 + 6/6 pass | 数据无变化, 但 A3 regression 暗示测试 gap (Mock 路径未覆盖) |
| 跟 Session 31 修复一致性 | 1 follow-up (P3 _BUILTIN_DIR monkeypatch) |

**未修前不写 "完成" / "PASS" / "12/12" / "OK" 字眼. 残余风险: 3 P1 待 user 拍板.**

---

## 修复落地 + 实证 (2026-06-26 主代理)

### 3 P1 全部修复

| ID | 修复 | 文件:行 | 测试覆盖 |
|:--|:--|:--|:--|
| **A1** | `TARGET_CONFIG_VERSION` 2.1.0 → 2.2.0 | `src/builderpulse/core/config.py:24` | `test_target_config_version_is_2_2_0` |
| **A3** | 恢复 `getattr(ctx.config, "prompts_dir", None)` 兜底 | `src/builderpulse/core/pipeline.py:151` | `test_step_summarize_handles_partial_config_mock` |
| **A4** | `_env_overridden` set 跟踪 + `to_dict(include_env_overrides=)` 参数 | `src/builderpulse/core/config.py:177-205` | `test_to_dict_excludes_env_overrides_by_default` + `test_to_dict_includes_env_overrides_when_requested` |

### 修复实证

**pytest 全量回归**: 616 pass + 4 skip (0 fail, 226s)
- 612 → 616: 加 4 测试（target_version / partial Config / to_dict exclude / to_dict include）

**REPL A1 实证**:
```python
from builderpulse.core.config import TARGET_CONFIG_VERSION
from builderpulse import __version__
assert TARGET_CONFIG_VERSION == __version__  # True ("2.2.0")
```

**REPL A4 实证**:
```python
import os
os.environ["BUILDERPULSE_PROMPTS_DIR"] = "/env/test"
c = Config.from_defaults()
assert c.prompts_dir == "/env/test"  # ✓ env 生效 in-memory
d = c.to_dict()  # 默认 include_env_overrides=False
assert "prompts_dir" not in d  # ✓ env 临时值不污染 disk
d2 = c.to_dict(include_env_overrides=True)
assert d2.get("prompts_dir") == "/env/test"  # ✓ 显式 dump 可拿
```

### 推进判定

**R1b 闭环 → R2 独立量化审计**。P2 (A2/A5/A6) + P3 (A7-A10) 全部 backlog。
