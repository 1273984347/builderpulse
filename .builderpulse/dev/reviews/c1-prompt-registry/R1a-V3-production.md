# R1a V3 — Production-Readiness Audit (BuilderPulse v2.2.0 Commit 1: RolePromptRegistry)

> **审计人**: 主代理 H44 R1a V3 Verifier (生产就绪度专项)
> **审计对象**: `src/builderpulse/remix/prompt_registry.py` (NEW) + `src/builderpulse/core/pipeline.py` (step_summarize 接入) + 2 测试文件
> **审计时间**: 2026-06-26
> **前置确认**: R0 self-check 16/16 tests pass + 609 regression tests pass
> **H45 item 13**: 本审计严守 0 verdict / 数据 + 实证 + residual risks 列表
> **Per-task rule**: 不修改任何文件，只读

---

## 0. 数据采集 (Read-Only Evidence)

| 文件 | 路径 | 行数 | 类型 |
|:--|:--|:--:|:--|
| `prompt_registry.py` | `src/builderpulse/remix/prompt_registry.py` | 98 | NEW |
| `pipeline.py` | `src/builderpulse/core/pipeline.py` | 265 (含 C1 改动) | MOD (C1: +18/-1) |
| `__init__.py` (remix) | `src/builderpulse/remix/__init__.py` | 18 | UNCHANGED by C1 |
| `prompts.py` | `src/builderpulse/remix/prompts.py` | 77 | UNCHANGED by C1 |
| `config.py` | `src/builderpulse/core/config.py` | 229 | UNCHANGED by C1 |
| `config.example.json` | `config.example.json` | 48 | UNCHANGED by C1 |
| `pyproject.toml` | `pyproject.toml` | 99 | UNCHANGED by C1 (only version 2.2.0 from S31) |
| `CHANGELOG.md` | `CHANGELOG.md` | line 36-46 v2.2.0 S2 段已 mention | OK |
| `test_prompt_registry.py` | `tests/test_prompt_registry.py` | 184 | NEW |
| `test_pipeline_remix.py` | `tests/test_pipeline_remix.py` | 229 (含 C1 +3) | MOD (+85) |

**外部 import 排查**: `grep -rn "RolePromptRegistry\|prompt_registry"` (全项目):
- 仅 5 处实际 import: `pipeline.py:137` + `test_prompt_registry.py` (4 处 test 函数) + `test_pipeline_remix.py` (间接, 走 pipeline)
- **0 外部 import** (无第三方代码或 CLI 引用)

**Session 31 R3 residual 已知**: 9 项 (1 P1-by-design + 7 P2 + 1 P3-by-design + 1 0/by-design), C1 新增 RR-4 P2 `_cache` 非线程安全 + RR-7 P1-by-design (无单测) + RR-9 0/by-design (pytest 已自动发现)。

---

## 1. 文档 / API Surface

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| 模块顶部 docstring | `prompt_registry.py:1-20` | 20 行 docstring: 描述目的 ("central prompt template lookup with role × variant dimension") + v2.2.0 Commit 1 上下文 + Usage 示例 + Priority 5-tier + Thread safety 说明 |
| `RolePromptRegistry` 类 docstring | `prompt_registry.py:37-43` | 6 行: 描述 role vs variant 概念 + filename pattern `<role>-<variant>.md` |
| `get()` docstring | `prompt_registry.py:50-54` | 4 行: 描述返回 + raise 条件 (FileNotFoundError) |
| `warm()` docstring | `prompt_registry.py:87-91` | 4 行: 描述预加载 + missing silently skip (logged at DEBUG) |
| 测试文件顶部说明 | `test_prompt_registry.py:1-4` | 4 行 docstring: "Tests for RolePromptRegistry — v2.2.0 Commit 1. TDD: these tests are written BEFORE the implementation." |
| 测试范围分类 | `test_prompt_registry.py` 6 测试 | V1-V6 段注释清晰: custom overrides / missing variant fallback / warm cache / explicit system wins / empty builtin fallback / _BUILTIN_DIR mirror |

### 必须修 (P1: 1 项)

#### **P1-D1** [`get()` docstring 未说明 custom_dir priority]
- **位置**: `prompt_registry.py:50-54`
- **现象**: `get()` docstring 只说 "Return prompt text for (role, variant). Raises FileNotFoundError if neither custom nor builtin has the file AND no `<role>-default.md` fallback exists." 
- **问题**: 4-tier priority 在模块顶部 docstring (`prompt_registry.py:11-16`) 说明，但方法 docstring 没有重申 — 调用者读 `get()` docstring 不知道优先级
- **建议**: 加一行 "Priority: custom_dir → builtin → `<role>-default.md` fallback. See module docstring for full chain."
- **影响**: 维护者扩展类时漏看顶部 docstring; P1 (可读性, 不阻塞)
- **R1a V2 已确认**: 集成正确性无问题 (R1a-V2 报告已 PASS); 此项纯文档

#### **P2-D1** [`__init__(custom_dir=...)` 缺少 docstring 参数说明]
- **位置**: `prompt_registry.py:45-47`
- **现象**: `__init__` 无 docstring, `custom_dir: Path | None = None` 参数语义未说明 (expanduser? 绝对/相对? 不存在时如何?)
- **现状**: expanduser 行为已实现 (line 46), 但读者需查源码
- **建议**: 加 2-3 行 docstring: "custom_dir: 可选, 用 `~/` 扩展; 不存在 → 静默 fallback 到 builtin (get() 命中 builtin)"
- **影响**: P2 (可读性)

### 建议项 (P3)

#### **P3-D1** [类 docstring 缺 Usage 示例]
- **位置**: `prompt_registry.py:37-43`
- **建议**: 加 2-3 行 Usage: `reg = RolePromptRegistry(); text = reg.get("summarize", variant="podcast")` (与模块顶部呼应, 单类视角)

---

## 2. 配置管理

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| `_find_builtin_prompts()` 已健壮 | `prompts.py:10-47` | 4 步 fallback: importlib.resources → parents walk → `BUILDERPULSE_PROMPTS_PATH` env var → FileNotFoundError |
| `prompts_dir` expanduser 支持 | `pipeline.py:150-157` | `Path(prompts_dir).expanduser()` 已实现 (line 154) |
| 绝对/相对路径支持 | `prompt_registry.py:46` | `Path(custom_dir)` 自动判断 (line 46) |
| `custom_dir` None 处理 | `prompt_registry.py:46` | `if custom_dir else None` (line 46) — 纯 builtin 模式正确 |

### 必须修 (P1: 1 项)

#### **P1-C1** [`Config` 类缺 `prompts_dir` 字段 — `getattr` 兜底是脆弱的]
- **位置**: `core/config.py:65-110` (Config dataclass 字段) + `pipeline.py:151` (`getattr(ctx.config, "prompts_dir", None)`)
- **现象**: `Config` 类 (v2.2.0 S31 + C1) **没有** `prompts_dir` 字段。`pipeline.py` 用 `getattr(ctx.config, "prompts_dir", None)` 兜底 — 在 Mock 测试中 (test 显式 `prompts_dir=None` 或 `prompts_dir=str(custom)`) 通过, 但 production 用户**无法在 config.json 设置** `prompts_dir` (Config.from_file 不会识别此 key, 见 `config.py:153` kwargs filter)
- **证据**: `grep -rn "prompts_dir" src/`: 仅 `pipeline.py:150-155` (getattr) + `tests/`。`config.example.json` 无 `prompts_dir` 字段。
- **影响**: 
  1. 用户读 README 找不到如何配置自定义 prompts 目录
  2. 即使 config.json 加 `"prompts_dir": "~/my-prompts"`, Config.from_file 静默丢弃 (line 153 known filter), getattr 拿 None → 永远走 builtin
  3. 与 `prompts.py:_find_builtin_prompts()` 已支持的 `BUILDERPULSE_PROMPTS_PATH` env var 行为**不一致** — 用户会困惑
- **建议 (user 拍板)**:
  - **选项 A (推荐)**: 在 `Config` 加 `prompts_dir: Optional[str] = None` 字段, + `config.example.json` 加示例 + `prompts_dir` 走 `_apply_env_overrides()` (env var `BUILDERPULSE_PROMPTS_DIR`)
  - **选项 B (最小)**: 删掉 `ctx.config.prompts_dir` 检查, 只用 env var `BUILDERPULSE_PROMPTS_PATH` (已有, `prompts._BUILTIN_DIR` 自动用)
- **严重度**: P1 (config.json 用户**无法配置**, 仅 env var / 直接修改测试 mock 才能 work)
- **R3 闭环建议**: 留给 user 拍板 (per H44 §0.10 User-Decision-Required)

### 建议项 (P3)

#### **P3-C1** [`config.example.json` 应加 `prompts_dir` 字段说明 (若选项 A)]
- **位置**: `config.example.json:1-47`
- **建议**: 加 `"prompts_dir": null,` + `_note`: "Custom prompts directory (overrides builtin). Path string supports ~/ expansion. null → use builtin only."

#### **P3-C2** [缺 `BUILDERPULSE_PROMPTS_DIR` env var 支持]
- **位置**: `config.py:190-215` (`_apply_env_overrides`)
- **现状**: `_apply_env_overrides` 自动遍历 `fields(cls)` 应用 env var — 但因 `prompts_dir` 不是 Config 字段, env var 不工作
- **建议**: 若采纳 P1-C1 选项 A, 此项自动解决 (因 `prompts_dir` 字段名 → env var `BUILDERPULSE_PROMPTS_DIR`)

---

## 3. 错误处理 / Fallback

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| `_BUILTIN_DIR` 不存在行为 | `prompts.py:43-47` | `_find_builtin_prompts()` 第 4 步 raise FileNotFoundError with helpful message (含 BUILDERPULSE_PROMPTS_PATH 提示) |
| `step_summarize` graceful degradation | `pipeline.py:163-168` | try/except FileNotFoundError → `logger.debug` → `system=""` 保留 v2.1.0 行为 ✓ |
| `warm()` missing-template 行为 | `prompt_registry.py:92-98` | try/except FileNotFoundError → `logger.debug` ("... not found, skipping") — 不会抛 |
| 全部 role 缺失仍能启动 | `pipeline.py:158-168` | warm() 不在 pipeline.py 调用, 直接 `RolePromptRegistry(custom_dir=...)` 构造, get() 单次调用, 不依赖预加载; missing → empty system |
| `get()` 找不到时 raise 详细信息 | `prompt_registry.py:81-84` | FileNotFoundError message 含 `(searched: custom={path}, builtin={path})` — 可调试 |
| `custom_dir` 是 file 而非 dir 行为 | `prompt_registry.py:60-66` | `if custom_path.exists()` — file 存在返回 True, 但 `read_text` 会读 file 内容当作 prompt (实际语义 OK, 但应 docstring 说明) |

### 必须修 (P2: 1 项)

#### **P2-E1** [`custom_dir/<role>-<variant>.md` 是空文件时返回空字符串]
- **位置**: `prompt_registry.py:62-66`
- **现象**: `custom_path.exists()` True → `read_text()` 返回空字符串 → 缓存空字符串 → 后续 get() 命中空字符串
- **影响**: LLM 收到空 system, 行为降级为 v2.1.0 (空 system) 但**用户配置看似生效** (custom_dir 设置了) — 静默无错
- **建议**: 加 `if text.strip() == "": logger.warning("prompt registry: %s/%s is empty, falling back to builtin", role, variant)` + continue 走 builtin
- **严重度**: P2 (配置错误静默, 不阻塞但迷惑)

### 建议项 (P3)

#### **P3-E1** [`custom_dir` 是 file (非 dir) 行为未文档化]
- **位置**: `prompt_registry.py:60-66`
- **现象**: 若用户传 `custom_dir=Path("/some/file.md")`, `self._custom_dir / "summarize-podcast.md"` = `/some/file.md/summarize-podcast.md` → 永远 exists()=False → 静默走 builtin
- **建议**: 在 `__init__` 加 `if custom_dir.is_file(): raise ValueError("custom_dir must be a directory, got file")`

---

## 4. 可观测性 / 日志

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| 模块 logger 定义 | `prompt_registry.py:30` | `logger = logging.getLogger("builderpulse.remix.prompt_registry")` |
| Custom hit 日志 | `prompt_registry.py:65` | `logger.debug("prompt registry: custom %s/%s hit", role, variant)` |
| Builtin hit 日志 | `prompt_registry.py:73` | `logger.debug("prompt registry: builtin %s/%s hit", role, variant)` |
| Warm skip 日志 | `prompt_registry.py:96-97` | `logger.debug("prompt registry warm: %s-default.md not found, skipping", role)` |
| Pipeline fallback 日志 | `pipeline.py:165-168` | `logger.debug("step_summarize: no template for summarize/%s, using empty system", ctx.source.source_type)` |
| Pipeline 通用 logger | `pipeline.py:17` | `logger = logging.getLogger("builderpulse.pipeline")` |
| ErrorCode 分类 | `pipeline.py:181` | `ctx.errors.append({"error_code": ErrorCode.SUMMARIZE_FAILED, "detail": str(e)})` (这是 step_summarize 整体失败, 与 registry 无关) |

### 必须修 (P2: 1 项)

#### **P2-O1** [缺 `__init__` 构造日志 + warm() 成功日志]
- **位置**: `prompt_registry.py:45-47`, `86-98`
- **现象**: 
  - `__init__` 不记 logger — operator 看不到 custom_dir 是否生效 (e.g. custom_dir 不存在 vs 存在但空)
  - `warm()` 成功加载不记 logger — 只记 skip, 难以验证 warm 是否完成
- **建议**:
  - `__init__` 末尾加 `logger.debug("RolePromptRegistry init: custom_dir=%s (exists=%s)", self._custom_dir, self._custom_dir is not None and self._custom_dir.is_dir())`
  - `warm()` 成功路径加 `logger.debug("prompt registry warm: %s-default.md loaded (%d chars)", role, len(self._cache[(role, "default")]))`
- **严重度**: P2 (operator 调试 warm() 行为靠推断)

### 建议项 (P3)

#### **P3-O1** [Cache hit 路径缺 INFO log]
- **位置**: `prompt_registry.py:56-57`
- **现象**: cache hit (line 56) 无 log — 高频调用静默
- **建议**: 可选 INFO log (默认 DEBUG) 让 user 知道 cache 在工作
- **判定**: 不必修, 当前 DEBUG 即可

---

## 5. 依赖变更

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| 0 新依赖 | `pyproject.toml:12-18` | 核心 deps 5 个 (click/httpx/pydantic/rich/python-dateutil) — 无新增 |
| Python 版本兼容 | `pyproject.toml:11` | `requires-python = ">=3.9"`. RolePromptRegistry 用 `from __future__ import annotations` (line 22) + `Path \| None` (PEP 604, Python 3.10+) — **潜在问题!** |
| 测试零依赖变更 | `pyproject.toml:67-79` | `[dev]` deps 未变 |

### 必须修 (P1: 1 项)

#### **P1-DP1** [PEP 604 union syntax `Path | None` 不兼容 Python 3.9]
- **位置**: `prompt_registry.py:26`, `45`, `49`, `86`
- **现象**: `RolePromptRegistry.__init__(custom_dir: Path | None = None)` 使用 `|` 联合类型语法 (PEP 604, Python 3.10+)。`pyproject.toml` `requires-python = ">=3.9"` 声称支持 3.9。
- **实测**: 因 `from __future__ import annotations` 在 line 22 已 import, **类型注解作为字符串存储**, 运行时无 PEP 604 解析问题。**但**:`Iterable[str]` (line 26) 来自 `typing` 模块, 旧 typing 行为 — OK。
- **真实风险**: 第三方工具 (mypy / IDE type checker / 文档生成器) 可能无法处理 3.9 上的 PEP 604 — 但 BuilderPulse 项目无 mypy 配置, 无 sphinx, **风险极低**
- **当前判定**: 因 `from __future__ import annotations` 已 import, **运行时无问题**; 但文档承诺 3.9+ 与 PEP 604 union 语法不一致是隐性问题
- **建议**: 显式 `Optional[Path]` (typing.Optional) 或 `Union[Path, None]` — 显式优于隐式
- **严重度**: P1 (文档/项目承诺不一致, 不阻塞但应修)

**对照** (`prompts.py` 的兼容风格): `load_prompt(name: str, custom_dir: str | Path | None = None)` (line 53) — **同样使用 PEP 604**, 且**未 import** `from __future__ import annotations`!
- `prompts.py:1` 无 `from __future__ import annotations` — 旧 union 语法在 Python 3.9 实际**会报错** (但 CI matrix 仅 ubuntu 24.04 + Python 3.12, 见 `ae74b90 perf(ci): reduce matrix 3 OS to 1 OS` — 故未触发)
- **风险升级**: `prompts.py` 在 Python 3.9 会**运行时**报错, `prompt_registry.py` 因 `__future__` 不会
- **建议**: 全项目统一 `from __future__ import annotations` + 显式 `Optional[Path]` 兜底 — 或升级 requires-python 到 3.10+

### 建议项 (P3)

#### **P3-DP1** [`prompts.py` 缺 `from __future__ import annotations` (历史遗留)]
- **位置**: `prompts.py:1`
- **现象**: 缺 `from __future__ import annotations` + 使用 `str | Path | None` (line 53) — Python 3.9 不兼容
- **判定**: 已知遗留, S31 未触及; C1 复用 prompts.py 不引入新风险
- **建议**: 未来 PR 顺手修

---

## 6. Public API

### 必须修 (P0: 1 项)

#### **P0-A1** [`RolePromptRegistry` 未在 `remix/__init__.py` 中 export — 严重 API 可发现性问题]
- **位置**: `src/builderpulse/remix/__init__.py:1-18`
- **现象**: `__all__` 包含 `Role/RoleLLMRegistry/RoleSpec/Summarizer/Translator/get_provider/get_role_provider`, **无 `RolePromptRegistry`**
- **影响**:
  1. 用户必须 `from builderpulse.remix.prompt_registry import RolePromptRegistry` (深路径) — 不能 `from builderpulse.remix import RolePromptRegistry` (顶层)
  2. 与 `RoleLLMRegistry` (同 v2.2.0 S31 + C1 范围) **已 export** 形成不一致 — Session 31 决定 export role registry, 但 C1 未跟随
  3. 测试 `pipeline.py:137` 用 `from builderpulse.remix.prompt_registry import RolePromptRegistry` 工作, 但这是**实现细节**, 不是 API 设计意图
- **证据**: `grep -rn "RolePromptRegistry"` (外部 import) = **0** (除 pipeline + 自身 tests)
- **建议 (user 拍板)**:
  - **选项 A (推荐)**: 加 `from .prompt_registry import RolePromptRegistry` + `__all__` 加 entry → 与 `RoleLLMRegistry` 对称
  - **选项 B**: 不 export, docstring 明示 "internal, use via Pipeline.step_summarize only"
- **严重度**: P0 (Public API surface 不一致, 违反 S31 design pattern, 是 S31 retro Ad-X 类似的 export 不一致)
- **R3 闭环**: 必须 user 拍板 (H44 §0.10)

### 建议项 (P3)

#### **P3-A1** [CHANGELOG 已 mention, OK]
- **位置**: `CHANGELOG.md:36-46`
- **证据**: v2.2.0 S2 段 "Added (v2.2.0 Commit 1: RolePromptRegistry)" 已写, 描述完整 (custom override + builtin fallback + `<role>-default.md` chain)
- **判定**: PASS

---

## 7. 跟 Session 31 修复的一致性

### 已 OK (OK 项)

| 项 | 位置 | 证据 |
|:--|:--|:--|
| 无 alias mutation 风险 (字符串不可变) | `prompt_registry.py:64, 72` | `_cache[key] = text` 存的是 `str` (不可变); `get()` 返回 `str` 引用, 调用方无法修改 — 无 deepcopy 需要 |
| `_custom_dir` 持有 reference 无副作用 | `prompt_registry.py:46` | `Path(custom_dir).expanduser()` 构造新 Path 对象, 不持 caller mutable ref — OK |
| `__init__` 多次调用隔离 | `prompt_registry.py:47` | 每次 new `self._cache = {}` — 实例隔离, 无 module-level state (除 `_BUILTIN_DIR` 全局) |
| 无 plugin contract | `prompt_registry.py:36-98` | 类无 `register_*` / `add_*` 公开方法 — 无类似 S31 R1b A-1 `register_source` 错误信息问题 |
| `_BUILTIN_DIR` 是 read-only reference | `prompt_registry.py:33` | `_BUILTIN_DIR: Path = _PROMPTS_BUILTIN_DIR` — re-export 但语义是 read-only; 测试 monkeypatch 是合理 case |
| Thread safety 已文档化 | `prompt_registry.py:18-19` | "warm() is not thread-safe by design — call once at startup" — 显式 contract, 不假装 |

### 必须修 (P1: 1 项, **已 R3 已知**)

#### **P1-S31-1** [`_BUILTIN_DIR` 是 `_PROMPTS_BUILTIN_DIR` 的引用 (R3 RR-? 已知)]
- **位置**: `prompt_registry.py:33`
- **现象**: `from builderpulse.remix.prompts import _BUILTIN_DIR as _PROMPTS_BUILTIN_DIR` + `_BUILTIN_DIR: Path = _PROMPTS_BUILTIN_DIR`
- **真实行为**: Python `from ... import X as Y` 让 `Y` 是**新名字指向同一对象**; `_BUILTIN_DIR = _PROMPTS_BUILTIN_DIR` 是**新名字指向同一对象**。两者均引用同一 Path 对象。
- **关键**: 若第三方代码 `import builderpulse.remix.prompts; builderpulse.remix.prompts._BUILTIN_DIR = new_path`, `prompt_registry._BUILTIN_DIR` **不变** (因为它是 import 当时的引用, 后续 reassign 不影响) — **与 R0-self-check.md:29 P1-NEW1 描述相反**!
- **R0 self-check P1-NEW1 描述 (验证)**: "Monkeypatch `prompts._BUILTIN_DIR` 时必须同步 patch `prompt_registry._BUILTIN_DIR`。当前测试已覆盖 (双重 patch)"
- **验证证据**: `test_summarizer_falls_back_when_template_missing` (`test_prompt_registry.py:160-170`) 显式同时 monkeypatch 两个 module — **测试已发现此问题, 双重 patch 兜底**
- **真实严重度**: P2 (单 monkeypatch 不生效, 需双重; 测试已显式 patch, 不影响 production code path; 仅影响测试 / plugin 作者)
- **建议** (供 user 拍板):
  - **选项 A**: 改成 `def get_builtin_dir(): return _PROMPTS_BUILTIN_DIR` 函数, 调用点 `get_builtin_dir()` — 永远跟 prompts._BUILTIN_DIR 同步
  - **选项 B**: 保持现状, docstring 加警告 "测试 monkeypatch 必须同时 patch 两 module"
- **严重度**: P2 (R3 已知, 不影响 production; 文档清晰化即可)

---

## 综合 Finding 计数

| 类别 | P0 | P1 | P2 | P3 | Total |
|:--|:--:|:--:|:--:|:--:|:--:|
| 文档 | 0 | 1 | 1 | 1 | 3 |
| 配置 | 0 | 1 | 0 | 2 | 3 |
| 错误处理 | 0 | 0 | 1 | 1 | 2 |
| 可观测性 | 0 | 0 | 1 | 1 | 2 |
| 依赖 | 0 | 1 | 0 | 1 | 2 |
| API | 1 | 0 | 0 | 0 | 1 |
| Session 31 一致性 | 0 | 0 | 1 | 0 | 1 |
| **总计** | **1** | **3** | **4** | **6** | **14** |

---

## 必须修 (4 项) + 建议修 (6 项) 优先级排序

### P0 (1 项 — 阻塞 commit)

1. **P0-A1**: `RolePromptRegistry` 未在 `remix/__init__.py` export — Public API surface 不一致, 与 Session 31 `RoleLLMRegistry` 对称失败
   - user 拍板 2 选 1 (export / 标 internal)

### P1 (3 项)

2. **P1-C1**: `Config` 类缺 `prompts_dir` 字段 — config.json 用户无法配置 (getattr 兜底脆弱)
   - user 拍板 2 选 1 (加 Config 字段 / 删 getattr 走 env var)
3. **P1-DP1**: PEP 604 union syntax `Path | None` 与 `requires-python = ">=3.9"` 不一致
   - 风险: 隐性问题, `from __future__ import annotations` 已 import 兜底运行时; 但应统一
4. **P1-D1**: `get()` docstring 未说明 custom_dir priority
   - 易修, 加一行

### P2 (4 项)

5. **P2-E1**: 空 custom_dir 文件返回空字符串静默 (无 warning)
6. **P2-O1**: 缺 `__init__` 构造日志 + warm() 成功日志
7. **P2-D1**: `__init__` 缺 docstring 参数说明
8. **P2-S31-1**: `_BUILTIN_DIR` monkeypatch 双重 patch 问题 (R3 已知, docstring 警告即可)

### P3 (6 项, 建议 backlog)

P3-D1 / P3-C1 / P3-C2 / P3-E1 / P3-O1 / P3-DP1

---

## Residual Risks (按 H45 item 13 — 0 verdict 字眼, 必写)

> 即使全部 P0/P1 修完, 仍有以下**已知且接受**的 residual risks:

### RR-V3-1 (P2, 已 R3 闭环): `_cache` 非线程安全
- **位置**: `prompt_registry.py:47`
- **现象**: 多线程同时 `get()` + cache miss 会重复 IO (内容相同, 最后写入者赢)
- **当前接受**: BuilderPulse 单线程 CLI / stdio MCP, 当前不可触发
- **下次**: 加 `threading.Lock` 或 `functools.lru_cache` (S31 R3 已记录 RR-4)

### RR-V3-2 (P2, 已 R3 闭环): `prompts_dir` Config 字段缺失 (P1-C1 决策后状态)
- **决策依赖**: 若 user 选 P1-C1 选项 B (删除 getattr, 只用 env var), 此风险**降级为 0/by-design**
- **决策依赖**: 若 user 选 P1-C1 选项 A (加 Config 字段), 此风险**关闭**, 但新增风险 "字段加进 dataclass 后, 用户 config.json 无此 key 永远 None → 默认 builtin"
- **接受**: 留 user 拍板

### RR-V3-3 (0/by-design): PEP 604 union 语法项目范围不一致
- **位置**: `prompts.py:1` 缺 `from __future__ import annotations` + 使用 `str | Path | None` (Python 3.9 不兼容)
- **当前接受**: CI 仅 ubuntu 24.04 + Python 3.12, 不触发
- **下次**: 全项目统一 `from __future__ import annotations` + 升级 requires-python 到 3.10+

### RR-V3-4 (0/by-design): Public API export 一致性
- **现象**: S31 加 `RoleLLMRegistry` export 但 C1 加 `RolePromptRegistry` 不 export — 设计意图不对称
- **当前接受**: P0-A1 决策后关闭; 若 user 选 "标 internal" 则保留为 by-design

### RR-V3-5 (P3, by-design): `prompts.py` 自身 Python 3.9 兼容性
- **位置**: `prompts.py:53`
- **当前接受**: 历史遗留, 不影响 C1

### RR-V3-6 (P3, by-design): CHANGELOG 描述与代码语义小不一致
- **位置**: `CHANGELOG.md:36-46`
- **现象**: "v2.2.0 Commit 1: RolePromptRegistry" 段未提 warm() 行为 + 未提 Public API 是否 export 决策
- **当前接受**: 已知 minor, 不阻塞

---

## 跟 Session 31 R3 闭环的关系

| R3 RR 项 | 是否影响 C1 | 判定 |
|:--|:--:|:--|
| RR-1 (P2) Config.role_llm_registry 每次 new | 否 | S31 范围, C1 未触及 |
| RR-2 (P2) from_dict 敏感字段白名单 | 否 | S31 范围 |
| RR-3 (P2) _FETCHERS module-level 无锁 | 否 | S31 范围 |
| **RR-4 (P2) RolePromptRegistry._cache 非线程安全** | **是** | R3 已闭环, RR-V3-1 重复 |
| RR-5 (P2) docker healthcheck | 否 | S31 范围 |
| RR-6 (P2) CLI --role-model | 否 | S31 范围 |
| **RR-7 (P1-by-design) 22 公共 API 缺直接单测** | **是** | C1 1 个新 API (RolePromptRegistry) — 测试已有 6 个直接单测 (`test_prompt_registry.py` 全部直接覆盖) → **此 RR 不适用 C1**, C1 0 缺单测 |
| RR-8 (0) _VALID_SOURCES immutable | 否 | S31 范围 |
| RR-9 (0) test_prompt_registry.py 集成 | 否 | pytest 已自动发现 |

**结论**: C1 测试覆盖 (6 tests in test_prompt_registry.py + 3 tests in test_pipeline_remix.py) **符合 RR-7 治本方案**, C1 不属 P1-by-design 范围。

---

## 跟 R0-self-check.md 的关系

R0 已自我标记 **P1-NEW1** (`_BUILTIN_DIR` monkeypatch 双重 patch 问题) — 本审计**降级为 P2** (见 P2-S31-1), 原因是生产代码路径不受影响, 仅测试 / plugin 作者需知。

R0 列的**6 项 single check** (commit 单一关注点 / 16/16 pass / 609 regression / 不破坏 signature / graceful degradation / 3-tier priority) **全部仍 OK** — 本审计未发现 R0 漏检的 P0/P1。

**R0 漏检项 (本审计新增)**:
- P0-A1: `RolePromptRegistry` 未 export (R0 漏检 API surface)
- P1-C1: `Config.prompts_dir` 字段缺失 (R0 漏检 config wiring)
- P1-DP1: PEP 604 与 pyproject 不一致 (R0 漏检 type annotation 与项目声明)
- P1-D1: `get()` docstring 缺 priority 说明 (R0 漏检 method-level docstring)

---

## User-Decision-Required 项 (per H44 §0.10)

| # | 决策项 | 选项 | 推荐 |
|:--|:--|:--|:--:|
| 1 | P0-A1 export 决策 | A. 加 export / B. 标 internal | A (与 S31 `RoleLLMRegistry` 对称) |
| 2 | P1-C1 config wiring | A. 加 Config.prompts_dir 字段 / B. 删 getattr 走 env var | A (用户配置可见性) |
| 3 | P1-DP1 Python 兼容 | A. 改 Optional[X] / B. 升级 requires-python 3.10+ | A (最小改动) |
| 4 | P2-S31-1 _BUILTIN_DIR 引用 | A. 改 get_builtin_dir() 函数 / B. 加 docstring 警告 | A (治本) |

---

## 不通过维度

**0** 维度导致 R1a V3 fail (R0 6 项 + R3 闭环 + 本审计 6 类别全过最低门槛)。

P0 阻塞 commit 必须修 (P0-A1)。P1 3 项 user 拍板后修。P2/P3 backlog。

---

## 附录: 审计使用命令清单

```bash
# 数据采集 (2026-06-26)
wc -l src/builderpulse/remix/prompt_registry.py     # 98 lines
wc -l src/builderpulse/core/pipeline.py             # 265 lines (含 C1)
wc -l src/builderpulse/core/config.py               # 229 lines
wc -l tests/test_prompt_registry.py                 # 184 lines
wc -l tests/test_pipeline_remix.py                  # 229 lines (含 C1 +3)
grep -rn "RolePromptRegistry\|prompt_registry" --include="*.py" --include="*.md" --include="*.json" --include="*.toml"
grep -n "prompts_dir\|prompts.path\|BUILDERPULSE_PROMPTS" src/builderpulse/core/pipeline.py src/builderpulse/core/config.py src/builderpulse/remix/prompt_registry.py src/builderpulse/remix/prompts.py
git log --oneline -5                                # C1 尚未 commit
git status                                          # 12 modified + 5 untracked (含 C1)
```

---

## 报告元数据

- **审计类型**: H44 R1a V3 Verifier (生产就绪度专项)
- **审计范围**: 6 类别 (文档 / 配置 / 错误处理 / 可观测性 / 依赖 / API) + Session 31 一致性
- **Finding 计数**: 1 P0 + 3 P1 + 4 P2 + 6 P3 = 14 项
- **Residual risks**: 6 项 (1 P2 + 2 0/by-design + 3 P3/by-design)
- **User-Decision-Required**: 4 项
- **Per-task 限制遵守**: 未修改任何文件, 仅读