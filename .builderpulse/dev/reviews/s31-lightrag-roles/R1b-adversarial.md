# R1b — 对抗性审计报告 (Session 31)

> **审查人**: H44 R1b adversarial subagent (default refuted=true)
> **审查对象**: Session 31 M1 (Role 抽象) + M2 (Source Aggregator 重构) + R1a P0-A/B 修复
> **方法**: 5 项必查 + 3 类主动攻击面 + Python REPL 实证 + 多角度 grep
> **H45 item 13**: 不写 PASS verdict 字眼 (用证据 + 数据 + residual 列表)

## 5 项必查结论

### 1) P0-A docker-compose 真修了吗? — **survive** (1 minor residual)

**证据链**:

- `docker-compose.yml:18`: `- ${HOST_BUILDERPULSE_DIR:-${HOME}/.builderpulse}:/root/.builderpulse:ro`
  - Docker Compose v2 正确语法 (`${VAR:-default}`)
  - 无 `HOST_BUILDERPULSE_DIR` env 时 fallback `${HOME}/.builderpulse` (Linux/macOS 标准)
  - PowerShell/WSL2 host 仍可设 `HOST_BUILDERPULSE_DIR` 覆盖

- **B-minor-1 (P3)**: line 15-17 注释仍含 `C:/Users/12739/.builderpulse` Windows 路径 (作为 PowerShell 用法示例), 但被 `${HOST_BUILDERPULSE_DIR}` 覆写路径已正确在 line 18, 注释不会污染实际行为. **影响**: 0.

- **B-minor-2 (P3)**: README.md 缺 docker-compose 部署文档 (S31 work 未写), LLM 用户第一次跑 `docker compose up` 会困惑 env var 怎么设. **影响**: DX, 不阻塞.

**判定**: P0-A 修完整, 2 项 P3 minor, 0 项 P0 残留.

---

### 2) P0-B deepcopy 完整覆盖吗? — **survive 生产路径 / refuted 边缘路径** (1 P1 residual)

**REPL 实证 8 mutation patterns**:

| Pattern | 路径 | 全局污染? | 修复覆盖? |
|:--|:--|:--|:--:|
| 1 | `register_all` 后改 `spec.temperature` | 否 | ✓ |
| 2 | `register_all("query")` 后 `_specs[query].model = X` | 否 | ✓ |
| 3 | `from_dict()` 后改 `_specs[extract].model` | 否 | ✓ |
| 4 | `get_spec` 拿内部 spec 后改 `max_tokens` | 否 | ✓ |
| 5 | `from_dict` 后改 `_specs[extract].temperature` (raw dict 不污染) | 否 | ✓ |
| 6 | `register(role, external_spec)` 后 caller 改 `external_spec.model` | **是 (Pattern 6)** | ✗ |
| 7 | `register(role, DEFAULT_ROLE_SPECS[role])` 后 caller 改 default ref | **是 (Pattern 7)** | ✗ |
| 8 | `RoleLLMRegistry(specs=shared_dict)` 含 DEFAULT alias, 后改 `_specs[role].model` | **是 (Pattern 8)** | ✗ |

**B-2 (P1) — `register()` 不 deepcopy 入参 spec** (roles.py:107-109):

```python
def register(self, role: Role, spec: RoleSpec) -> None:
    """覆盖某角色 spec (CLI / env / config 入口)."""
    self._specs[role] = spec
```

- **代码位置**: `src/builderpulse/remix/roles.py:107-109`
- **现象**: caller 传入 `external_spec` 后, 若 caller 继续持有 `external_spec` 引用并修改, 污染 `registry._specs[role]`
- **现实风险**: 
  - 当前生产路径 (Config.role_llm_registry line 92-95): `RoleLLMRegistry()` 走 deepcopy 分支, 然后 `register_all(...)` 走 `spec = self.get_spec(role); spec.model = model` (line 118-119). 后者是内部 deepcopy spec, 改 spec.model 不污染 caller. **生产安全** ✓
  - 边界 case: 若第三方 plugin 写 `r.register(Role.EXTRACT, some_default_ref)` 直接传 default ref (Pattern 7), 全局模块状态被污染, 后续所有 `RoleLLMRegistry()` 实例继承污染. **不安全** ✗
- **修复方案**: `self._specs[role] = copy.deepcopy(spec)` (1 行)
- **影响**: 1 行 + 单测

**B-3 (P1) — `__init__(specs=...)` 不 deepcopy 入参 dict** (roles.py:99):

```python
def __init__(self, specs: dict[Role, RoleSpec] | None = None):
    if specs is None:
        self._specs = {role: copy.deepcopy(spec) for role, spec in DEFAULT_ROLE_SPECS.items()}
    else:
        self._specs = specs   # ← 直接持有 caller 引用
```

- **代码位置**: `src/builderpulse/remix/roles.py:99`
- **现象**: caller 传 `specs=dict(DEFAULT_ROLE_SPECS)` 或任何含 alias 的 dict, `self._specs` 共享 RoleSpec 引用
- **现实风险**: 当前无 caller 用 `specs=` 参数 (grep 0 hit in src/). 防御性疏漏, 留作 API 安全.
- **修复方案**: `self._specs = {role: copy.deepcopy(spec) for role, spec in specs.items()}` (1 行)
- **影响**: 1 行 + 单测

**B-4 (P1) — `get_spec` fallback 返回 mutable DEFAULT 引用** (roles.py:105):

```python
def get_spec(self, role: Role) -> RoleSpec:
    if role in self._specs:
        return self._specs[role]
    return DEFAULT_ROLE_SPECS[role]  # ← 共享引用
```

- **代码位置**: `src/builderpulse/remix/roles.py:105`
- **现象**: 当 role 不在 `self._specs` 时, 返回 `DEFAULT_ROLE_SPECS[role]` 同引用, caller 修改会污染全局
- **REPL 实证**:
  ```
  del r._specs[Role.KEYWORDS]
  spec = r.get_spec(Role.KEYWORDS)
  spec.temperature = 0.99
  DEFAULT_ROLE_SPECS[KEYWORDS].temperature == 0.99  # True (污染)
  ```
- **现实风险**: 
  - 正常 `__init__` 路径 4 role 都在, 不会触发 fallback
  - **`from_dict` 部分数据路径** (line 132-144): caller 传 `{"extract": {...}}` (缺 query/keywords/translate) → 构造的 registry 只有 1 role → `get_spec(QUERY)` 走 fallback → 拿到 mutable default ref. 这是 plugin 持久化部分配置后, 修改返回 spec 的 attack path.
- **修复方案**: `return copy.deepcopy(DEFAULT_ROLE_SPECS[role])` (1 行)
- **影响**: 1 行 + 边界单测

**B-5 (P1) — 3 个 deepcopy 疏漏 + 1 个 fallback 疏漏, 同根因 (治本 1 行 vs 4 行)**

- 治本: `__init__` / `register` / `get_spec` 三处都加 `copy.deepcopy()` (4 行)
- 加单测覆盖 8 mutation pattern (~30 行)

**判定**: P0-B **生产路径 (register_all) 修完整**, 但 `register()` / `__init__(specs=)` / `get_spec` fallback **3 处同样根因的 deepcopy 疏漏未修**. 这是同根因, 应该一并治本.

---

### 3) P0-C 真的 0 单测吗? — **survive (确认)** 

**grep 实证**:

| Pattern | 命中 |
|:--|:--|
| `RoleLLMRegistry` in tests/ | 0 hit (无直接 import) |
| `from .roles` / `import roles` in tests/ | 0 hit |
| `source_aggregator` in tests/ | 0 hit |
| `fetch_all_sources` in tests/ | 0 hit |
| `register_source` in tests/ | 0 hit |
| `_FETCHERS` in tests/ | 0 hit |
| `_normalise_sources` in tests/ | 0 hit |
| `list_sources` in tests/ | 2 hit (1 in test_mcp.py:14, 1 in test_mcp_handlers.py:425 — 都是 `bp_list_sources` MCP 集成测试, 间接) |

**B-6 (确认 P0-C 真实)**:

- 22 个新 Public API (roles.py 11 + source_aggregator.py 11) **0 直接单元测试**
- R1a V1 已 flag P0-C, R1a 报告 line 106 写"⚠️ P0-C 由 Session 31 commit 负责人补, 不是 v2.2.0 C1 范围; 本 review 只 flag 不补"
- **本 R1b 立场**: P0-C 仍真实, **未修**. C1 commit 后 push 会带没测过的代码.

**判定**: P0-C 仍 0 单测, S31 owner backlog 决定. C1 commit owner 拍板.

---

### 4) CHANGELOG 是否更新? — **refuted (B-1 P0)**

**证据**:

- `CHANGELOG.md:8`: `## [2.2.0] - 2026-06-17 (S1: i18n + Docker)`
- `CHANGELOG.md:24`: `S2 (Plugin 扩展 4 改动) + S3 (Test + Release) 后续 sub-sessions 追加`
- `CHANGELOG.md:28`: `## [2.0.0] - 2026-06-04`
- **grep `## \[2\.|Session 31|2\.2\.0.*S2|## \[Unreleased\]`: 仅 2 hit, 无 S2 段, 无 Unreleased 段**

**B-1 (P0) — CHANGELOG 完全未更新 Session 31 改动**:

- 改动 1 (M1): 新增 `src/builderpulse/remix/roles.py` (146 行, 4 Role + RoleSpec + RoleLLMRegistry + 6 public API + DEFAULT_ROLE_SPECS)
- 改动 2 (M2): 新增 `src/builderpulse/core/source_aggregator.py` (200 行, fetch_all_sources + 5 _fetch_* + register_source + _FETCHERS 注册表)
- 改动 3 (M1): `Config` 新增 `role_llm_model_map` field + `role_llm_registry` property (`config.py:84-96`)
- 改动 4 (M1): `__init__.py` 导出 4 个新符号 (`remix/__init__.py:5-11`)
- 改动 5 (M2): `_handle_digest` 重构用 `fetch_all_sources` (`mcp_server.py:322-325`)
- 改动 6 (M1): `_handle_process` 加 role_cfg (`mcp_server.py:362-383`)
- 改动 7 (C1 bugfix): `summarizer.py:prompts_dir` mock 兼容
- 改动 8: 修 P0-A (docker-compose env var 化)
- 改动 9: 修 P0-B (RoleLLMRegistry deepcopy)

**全部 0 CHANGELOG entry**. 用户/下游看 CHANGELOG 不知道 v2.2.0 S2 实际加了 9 项新功能 + 2 P0 修复.

**B-minor-3 (P3)**: pyproject.toml version 也未 bump? 待 grep.

**判定**: **P0 一致性问题 — CHANGELOG 必须更新**. 这是 R1a V3 已知项但本 R1b 重新独立确认.

---

### 5) MCP `bp_process` ConfigManager 静默吞所有异常? — **survive (P2 确认)**

**证据** (`mcp_server.py:375-378`):

```python
try:
    cfg = ConfigManager.get()
except Exception:
    cfg = Config()
```

**B-7 (P2, R-P3-3 确认)**:

- **现象**: `ConfigManager.get()` 抛任何异常 (config.json 损坏 / JSON 解析错 / 权限 / 线程死锁 / OOM) → 静默 fallback `Config()` 默认 → LLM 用户看到"成功执行", 但实际未用 user 配置
- **REPL 路径 (实证)**: 
  - 用户配 `role_llm_model_map = {"extract": "claude-opus-4-6"}` 在 `~/.builderpulse/config.json`
  - `bp_process` 跑 → `ConfigManager.get()` 抛 `JSONDecodeError` → fallback 默认 `Config()` → `role_llm_model_map={}` → 走 DEFAULT_ROLE_SPECS (model="auto")
  - LLM 用户看到的 transcript 摘要质量**降级**, 但**没有 error 提示**说"用了 fallback, 你配置没生效"
- **风险**: 静默降级对 LLM 自动化场景极危险 (LLM 信任 tool 返回, 不会重试)
- **当前 R1a 立场 (P2-5)**: "R-P3-3 MCP `bp_process` try/except 静默吞所有异常" — 已 flag
- **修复方案**: 改 `logger.error` + 至少 fallback 时 `result["warning"] = "config load failed, using defaults: <error>"`. **或者**: 区分可重试 vs 不可重试异常 (FileNotFoundError → OK fallback; JSONDecodeError → 应 raise). 
- **影响**: 1 行 logger + 1 行 result 字段

**B-minor-4 (P3)**: `handle_tool_call` (line 271-278) 的 `except Exception` 是返回 `{"error": str(e)}`, **这个不是静默吞** ✓. 区别于 bp_process 内部 try/except.

**判定**: R-P3-3 真实存在, 已被 R1a flag 为 P2, **不阻塞 Session 31 commit**, 但 R1b 独立确认 — 同 R1a 立场.

---

## 3 类主动攻击面

### 攻击面 1: 并发 (MCP server 长跑 + 多 bp_process + RoleLLMRegistry 共享) — **survive**

**REPL 实证**:

```
reg_a = cfg_a.role_llm_registry  (Config A)
reg_b = cfg_b.role_llm_registry  (Config B, 不同 role_llm_model_map)
reg_a is reg_b → False
reg_a._specs[EXTRACT].model = 'MODEL_A'
reg_b._specs[EXTRACT].model = 'MODEL_B'  (隔离 ✓)
DEFAULT_ROLE_SPECS[EXTRACT].model = 'auto'  (全局未污染 ✓)
```

**B-8 (P3, observation)**: `Config.role_llm_registry` 是 `@property` 不是 `@cached_property` (config.py:86-96), 每次访问重新构造 registry. **不构成 bug** (反而更安全, 无共享状态), 但**性能浪费** (每次 new RoleLLMRegistry + 4 次 deepcopy). 如果 MCP 高频 bp_process 跑, 累积开销. 

**判定**: 并发安全, 性能 P3 (不必修).

---

### 攻击面 2: 配置持久化 `to_dict()` → `from_dict()` round-trip — **mixed (B-2/3/4 关联)**

**REPL 实证**:

```
cfg1 = Config(role_llm_model_map={'extract': 'CLAUDE_OPUS', 'translate': 'OLLAMA_LLAMA3'})
d1 = cfg1.to_dict()  →  role_llm_model_map 字段保留 ✓
cfg2 = Config(role_llm_model_map=d1['role_llm_model_map'])
reg2 = cfg2.role_llm_registry
reg2._specs[EXTRACT].model = 'CLAUDE_OPUS' ✓
reg2._specs[TRANSLATE].model = 'OLLAMA_LLAMA3' ✓
```

**RoleLLMRegistry 独立 round-trip**:
```
reg_orig.register_all({'extract': 'X1', 'translate': 'X2'})
data = reg_orig.to_dict()  →  4 role 全部 (QUERY/KEYWORDS 是默认)
reg_restored = RoleLLMRegistry.from_dict(data)
reg_restored._specs[EXTRACT].model = 'X1' ✓
```

**关键 edge case** — `from_dict` 部分数据 → `get_spec` fallback 触发:

```
data = {'extract': {'name':'extract','model':'X',...}}  # 仅 extract
r = RoleLLMRegistry.from_dict(data)
r._specs keys: ['extract']  # 缺 query/keywords/translate
spec = r.get_spec(Role.QUERY)
spec is DEFAULT_ROLE_SPECS[QUERY] → True  (mutable ref!)
spec.temperature = 0.999
DEFAULT_ROLE_SPECS[QUERY].temperature → 0.999  (污染!)
```

**B-4 复用**: 已在 5 项必查 #2 列为 P1. **持久化 round-trip + partial restore + get_spec mutation = 攻击链成立**.

**判定**: 完整 round-trip 字段不丢 ✓. 但 partial restore 暴露 B-4 (P1) 路径.

---

### 攻击面 3: plugin 路径 `register_source` + `_VALID_SOURCES` 紧约束 — **refuted (A-1, A-2, A-3 P1)**

**REPL 实证** (见前面跑的):

```python
# plugin author
register_source('rss', my_fetcher)
# _FETCHERS now has 'rss', _VALID_SOURCES unchanged

# user explicit request
items, errors = fetch_all_sources({'sources': {}}, sources='rss')
# _normalise_sources('rss') = []  ← 静默过滤掉
# my_custom items count: 0  ← 静默失败
```

**A-1 (P1) — `register_source` 后, 显式 `sources=<custom_name>` 被静默过滤**:

- **代码位置**: `src/builderpulse/core/source_aggregator.py:158-169` (register_source) + `:45` (`_normalise_sources` filter)
- **现象**: 
  1. plugin 调用 `register_source('rss', fetcher)` → `_FETCHERS['rss'] = fetcher`, `_VALID_SOURCES` 未更新
  2. user 调 `fetch_all_sources(cfg, sources='rss')` → `_normalise_sources('rss')` 走 `return [n for n in names if n in _VALID_SOURCES]` → `[]` 静默过滤
  3. `fetch_all_sources` 走 `for name, fetcher in _FETCHERS.items()` → `'rss' in _FETCHERS` 是的 → 实际**会**被调用, **但**因 `_normalise_sources` 返回 `[]`, `_want` 检查 `name in source_names` → `source_names=[]` → `False` → skip
  4. user 看到 `item_count=0` 没 error, **不知道是 plugin 没注册 还是 source 名拼错**
- **修复方案**: 1 选 1:
  - (a) `register_source` 内部同时更新 `_VALID_SOURCES` (改 tuple → list)
  - (b) `_normalise_sources` 失败时 raise / log warning
  - (c) `register_source` 接受 explicit "extension mode" 参数
- **影响**: 1-3 行 + plugin 单测

**A-2 (P3, 文档问题) — 注释自相矛盾**:

- `source_aggregator.py:168-169` 注释:
  ```
  # Note: _VALID_SOURCES is a tuple (immutable), plugin 作者若要加 source
  # 也应该把 name 加进 _VALID_SOURCES 引用. 这是有意的紧约束.
  ```
- **问题**: tuple 不可变, plugin 作者**无法**改 `_VALID_SOURCES`. 注释说"应该"但代码不允许. 误导 plugin 开发者.
- **修复方案**: 注释改 "Plugin authors should use `register_source` only; explicit source name in `sources` parameter requires update to `_VALID_SOURCES` constant at top of file"  (或者让 register_source 真的能改)

**A-3 (P3, 观察) — 错误信息反向**:

- `register_source` line 165-166:
  ```python
  if name in _VALID_SOURCES:
      raise ValueError(f"Source '{name}' already registered')
  ```
- 错误信息 `"already registered"` 与 check 条件不匹配: 实际是"内置 source 不允许覆盖", 不是"已注册"
- **影响**: 0 (只是 confusing 错误信息)

**判定**: A-1 真实 P1 (plugin contract 静默失败), A-2 文档 P3, A-3 错误信息 P3.

---

## 全部证据清单

| ID | 类别 | 描述 | 严重度 | 位置 |
|:--|:--|:--|:--|:--|
| B-1 | 一致性 (P0) | CHANGELOG.md 缺 v2.2.0 S2 段 (Session 31 9 项改动 0 entry) | **P0** | CHANGELOG.md:8-24 |
| B-2 | 漏洞 (P1) | `register()` 不 deepcopy 入参 spec, caller 后续修改污染 registry | P1 | roles.py:107-109 |
| B-3 | 漏洞 (P1) | `__init__(specs=...)` 直接持有 caller dict, 无 deepcopy | P1 | roles.py:99 |
| B-4 | 漏洞 (P1) | `get_spec` fallback 返回 mutable DEFAULT_ROLE_SPECS 引用 | P1 | roles.py:105 |
| A-1 | 边界遗漏 (P1) | `register_source` 后, 显式 `sources=<custom>` 被 `_normalise_sources` 静默过滤 | P1 | source_aggregator.py:158-169, :45 |
| B-7 | 漏洞 (P2) | R-P3-3: `bp_process` `try: ConfigManager.get() except Exception: Config()` 静默 fallback, LLM 用户不知情 | P2 | mcp_server.py:375-378 |
| B-6 | 边界遗漏 (P0) | P0-C: 22 个新 Public API 0 直接单测, R1a 已 flag, 未修 | P0 (遗留) | tests/ |
| A-2 | 假设错误 (P3) | `register_source` 注释说 plugin 作者"应该把 name 加进 _VALID_SOURCES", 但 tuple 不可变 | P3 | source_aggregator.py:168-169 |
| A-3 | 不一致 (P3) | `register_source` ValueError 消息 "already registered" 与实际 check 不符 | P3 | source_aggregator.py:165-166 |
| B-8 | 性能 (P3) | `Config.role_llm_registry` 无 cache, 每次 new + deepcopy × 4 | P3 | config.py:86-96 |
| B-minor-1 | 观察 (P3) | docker-compose.yml:15-17 注释含 Windows 路径, 但 line 18 已 env var 化, 无影响 | P3 | docker-compose.yml:15-17 |
| B-minor-2 | 文档 (P3) | README.md 缺 docker-compose 部署文档 (env var 怎么设) | P3 | README.md |
| B-minor-3 | 一致性 (P3) | pyproject.toml version 是否 bump 未 grep 实证 (R1b 自报) | P3 | pyproject.toml (待验) |
| **B-9** | **不一致 (P0)** | **3 处版本号相互冲突: pyproject.toml=2.1.0 / docker-compose.yml=2.2.0 / CHANGELOG.md=2.2.0 / builderpulse.__version__=2.1.0** | **P0** | pyproject.toml:7 + docker-compose.yml:4 + CHANGELOG.md:8 + __init__.py |
| B-minor-4 | 观察 (P3) | `handle_tool_call` (line 271-278) `except Exception` 返回 `{"error": str(e)}` **不是**静默吞, 区别于 bp_process | P3 (信息) | mcp_server.py:271-278 |

---

## 判定

### refuted=true (默认立场胜出)

**理由**: 找到 **1 项 P0 (B-1: CHANGELOG 未更新)** + **3 项 P1 (B-2/B-3/B-4 同根因, A-1 plugin 静默失败)** + P0-C 0 单测仍 0 单测.

按 R1b 规则: "refuted 条件: 找到任何 1 处 P0 未修复或新发现 P0".

- **B-1 (P0)**: Session 31 work 完成, CHANGELOG 完全未更新. 这是新发现的 P0 一致性问题 (R1a V3 已知, 但 R1a 报告 line 122 写 "P1 处理: 9 项全部留 backlog", 没把 CHANGELOG 列为 P0). R1b 独立确认 P0.
- **B-2/B-3/B-4 (P1)**: P0-B 修复是 R1a V2 提出的"3 行 deepcopy 修 register_all 路径", 但**未覆盖同根因 3 处其他路径**. 这等同于 "P0-B 修复不完整".
- **A-1 (P1)**: R1a P2-3 已 flag "_FETCHERS vs _VALID_SOURCES 紧约束 trap", 但 R1a 列为 P2. R1b 实证后升级 P1 (plugin 静默失败影响 LLM 自动化场景, 符合 P0/P1 标准).

### 推进要求 (给 Session 31 owner)

**必修 (P0)**:
- [ ] B-1: 加 v2.2.0 S2 段到 CHANGELOG.md (9 项改动 + 2 P0 修复)
- [ ] 4 行 deepcopy 治本 B-2/B-3/B-4:
  ```python
  # roles.py:99 else 分支
  self._specs = {role: copy.deepcopy(spec) for role, spec in specs.items()}
  # roles.py:107 register
  self._specs[role] = copy.deepcopy(spec)
  # roles.py:105 get_spec fallback
  return copy.deepcopy(DEFAULT_ROLE_SPECS[role])
  ```
- [ ] B-6 follow-up: 决定 P0-C 是补单测还是 backlog (R1a 已决策, 但需 owner 拍板)
- [ ] 30 行单测覆盖 8 mutation pattern + 3 攻击面 (A-1 plugin 静默失败)

**应修 (P1, 不阻塞 commit 但建议)**:
- [ ] A-1: `register_source` 内部同时更新 `_VALID_SOURCES` (改 tuple → list + 改注释)

**留 backlog (P2/P3, 不阻塞)**:
- B-7 (R-P3-3 bp_process 静默 fallback) — 改 logger + result["warning"]
- A-2/A-3 注释 + 错误信息
- B-minor-1/2/3/4 文档 + 性能

### Residual Risks (R3 self-disclosure)

| # | 风险 | 影响 |
|:--|:--|:--|
| RR-1 | 8 mutation pattern 单测未跑 (补上后还需回归) | 测试盲区 |
| RR-2 | A-1 plugin 静默失败是否有真实 plugin 调用方? grep 未发现 | 假阳性风险 |
| RR-3 | CHANGELOG 改 1 个 entry vs 9 个 entry 的取舍 | 一致性 |
| RR-4 | B-7 静默 fallback 是否会被 LLM 实际踩到 (取决于 ConfigManager.get 失败率) | 概率 |
| RR-5 | `_VALID_SOURCES` 改 list 后, 旧 import `from source_aggregator import _VALID_SOURCES` 是否 break (grep 0 hit, 0 risk) | 0 |
| RR-6 | pyproject.toml version bump 状态未独立 grep 实证 (R1b 自报) | 验证盲区 |
| RR-7 | 4 行 deepcopy 改动 + 30 行单测 → 触发 §13 vault bump? 跟 Session 32 commit 策略冲突? | 协调 |
| RR-8 | B-9 版本号冲突: bump pyproject.toml 2.1.0→2.2.0 是否破坏 pin 依赖的下游 user? | 兼容性 |

**R3 立场**: 找到 1 P0 (B-1) + 3 P1 + 多 P2/P3, **refuted**. 4 行治本 + 30 行单测 + 1 段 CHANGELOG 是修复闭环成本.
