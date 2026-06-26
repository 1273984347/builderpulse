# R1a V2 — 集成正确性专项 (Commit 1: RolePromptRegistry)

> **范围**: RolePromptRegistry 集成到 `step_summarize` 的接口正确性
> **时间**: 2026-06-26 (H44 R1a V2 inline)
> **焦点**: 与现有代码（`get_provider` / `Summarizer` / `AnthropicProvider` / CLI / MCP / Config / 旧测试）的集成接口
> **判定格式 (H45 item 13)**: 不写 PASS / 完成 / OK. 用 "数据 + 实证 + residual risks" 代替

---

## 1. 调用链绘制

```
[入口]
  CLI:    cli.py:296  bp process --url X --summarize --deliver Y
  MCP:    mcp_server.py:351  _handle_process(url, pipeline="transcribe", deliver=None)
  Direct: tests/test_pipeline_remix.py + tests/test_pipeline.py

[Step 0] URL → SourceRef
  SourceRef.from_url(url)                    cli.py:333  / mcp_server.py:382
  (新 source_type 解析 — 5 大 source plugin 入口)

[Step 1] Pipeline 构造
  cfg = Config(role_llm_model_map=...)       cli.py:337  / mcp_server.py:380
  p = Pipeline(config=cfg)                   cli.py:338  / mcp_server.py:383
  p.add(step_summarize)                      cli.py:342  / mcp_server.py:391

[Step 2] Pipeline.run(source)                pipeline.py:50
  ctx = PipelineContext(source, config)      pipeline.py:52
  for step in steps: ctx = step(ctx)         pipeline.py:54-67

[Step 3] step_summarize(ctx)                 pipeline.py:117
  ├─ read ctx.transcript.text                pipeline.py:131
  ├─ Role provider (S31):                    pipeline.py:140-146
  │   ├─ if hasattr(config, "role_llm_registry")
  │   │     provider = get_role_provider(Role.EXTRACT, ...)
  │   └─ else  provider = get_provider(model=config.model)
  │
  ├─ Prompt template (C1 NEW):               pipeline.py:148-168
  │   ├─ prompts_dir = getattr(config, "prompts_dir", None)  ← 仅 mock config 有
  │   ├─ if isinstance(prompts_dir, str) and prompts_dir:
  │   │     custom_prompts = Path(prompts_dir).expanduser()
  │   └─ registry = RolePromptRegistry(custom_dir=custom_prompts)  pipeline.py:158
  │       ├─ try: system = registry.get("summarize", variant=ctx.source.source_type)
  │       └─ except FileNotFoundError: system = "" (graceful)
  │
  └─ summarizer.summarize(text, system=system)  pipeline.py:170-177
      └─ retry(summarizer.summarize, ...)     pipeline.py:171 (max_retries=3)

[Step 4] Summarizer.summarize                summarizer.py:116
  if len(text) <= chunk_size:
    return provider.complete(text, system=system)  summarizer.py:118
  else:  # Map-Reduce
    for chunk: provider.complete(chunk, system=system)

[Step 5] Provider.complete(prompt, system)
  ├─ AnthropicProvider.complete              summarizer.py:54
  │   └─ anthropic.Anthropic.messages.create(
  │        system=system or "You are a helpful assistant."  summarizer.py:59
  │     )
  ├─ OpenAIProvider.complete                 summarizer.py:29
  │   └─ openai.chat.completions.create(messages=[{role:system, content:system}, ...])
  └─ OllamaProvider.complete                 summarizer.py:70
      └─ httpx.post /api/generate  payload["system"] = system  (if system)
```

---

## 2. 5 类集成风险逐项评分

### 风险 #1: Signature 兼容 — `step_summarize(ctx) → ctx`

**评分**: P0 (PASS by design) → P3 (low risk) 〔无新增风险〕

**实证**:
- `pipeline.py:117` `def step_summarize(ctx: PipelineContext) -> PipelineContext:` — 签名未改
- `Pipeline.run()` `pipeline.py:50-69` 仍消费 `Callable[[PipelineContext], PipelineContext]`,契约保留
- `PipelineContext` dataclass `pipeline.py:20-34` 字段未删
- 旧测试 `test_pipeline.py:71-79` (`test_step_summarize_without_transcript`) **仍 pass** (22/22 in pipeline+remix+registry 套件)
- 旧 Mock 模式 `Mock(model="gpt-4", api_key="test", language="zh")` `test_pipeline_remix.py:12` 仍可用 — 我的 R1a V2 实证 (E92 实证):
  ```
  5 results: ['OUT0', 'OUT1', 'OUT2', 'OUT3', 'OUT4']
  all OK: True
  ```

**残余风险** (P3): 1 项
- **R-V2-1 (P3)**: `from unittest.mock import Mock` 在 mock config 缺 `role_llm_registry` 时, `hasattr(ctx.config, "role_llm_registry")` → Mock 自动返回 truthy Mock 对象,**不会**走 `get_role_provider` 路径,而是 fallthrough 到 `get_provider` (实际效果正确,因 Mock 走 hasattr → truthy → 走 Role 分支 → 调 `get_role_provider` 内部 get_provider 同样被 mock). 我已实证 `test_step_summarize_calls_llm` 通过. **降级为 P3**: mock spec 没有 `role_llm_registry` 时,hasattr 返回 True 但 mock object is not None — pipeline 走 role 分支,触发 `get_role_provider` (mock.get_role_provider call 真实 → 内部又调真实 `get_provider` 又被 `@patch` 截). 实际测试通过,但 docstring 注释 `if hasattr(...) and ctx.config.role_llm_registry:` 的语义在 mock 下有点 fragile.

### 风险 #2: 状态污染 — `RolePromptRegistry._cache` 多 pipeline.run() 间累积/泄漏

**评分**: P3 (low risk) 〔设计正确,无累积〕

**实证**:
- `pipeline.py:158` `registry = RolePromptRegistry(custom_dir=custom_prompts)` — **每次** `step_summarize` 调用都构造新实例
- `RolePromptRegistry.__init__` `prompt_registry.py:45-47`: `self._cache: dict[tuple[str, str], str] = {}` — 全新空 dict
- `_custom_dir` 也每次重新 `Path(...).expanduser()` — 不可变
- 5 次连续 step_summarize 实证:
  ```
  5 results: ['OUT0', 'OUT1', 'OUT2', 'OUT3', 'OUT4']
  all OK: True
  ```
- 跨 call 缓存无累积 (因为新 instance)

**线程安全实证** (8 thread × 50 calls on cold cache):
```
errors: []
cache size: 1   (single entry, only 1 unique (role, variant) requested)
```
- CPython GIL 保护 dict `__setitem__` 原子性,实测无 race
- 注释 `prompt_registry.py:18-19` 声称 "cache dict is read-only after warm() finishes" — **但 warm() 在生产代码中从未被调用** (R-V2-2 below),所以 cache 在 get() 路径上是 **写后读**,不是只读

**残余风险** (P3): 2 项
- **R-V2-2 (P3)**: `RolePromptRegistry.warm()` 公开 API 但生产代码 (cli.py / mcp_server.py / pipeline.py) **无任何调用**. warm() 预热在多 source_type 大批量场景下理论可提速,但本版本未启用. docstring 与实现脱节. **降级 P3**: 未来性能优化点.
- **R-V2-3 (P3)**: 模板文件运行时修改不被 cache 感知 (E92 实证: `VERSION 1` → 写 `VERSION 2` → 仍返回 `VERSION 1`). by design (docstring 18-19), 风险在于 if user 在运行中改 `~/.builderpulse/prompts/summarize-podcast.md` 不生效. CLI/MCP 走一次性短进程,实际不会触发. **降级 P3**: 长期运行 daemon 才需 worry.

### 风险 #3: 配置 fallback — `ctx.config.prompts_dir` None / str / Path 各种类型

**评分**: **P2** 〔含 1 个 P2 风险,死代码 + Path-object 静默丢〕

**实证**:
- `Config` dataclass `config.py:65-117` **完整字段列表**:
  ```
  ['language', 'engine', 'model', 'device', 'workspace',
   'role_llm_model_map', 'version', 'enabled_sources',
   'enabled_channels', 'sources_config', 'channels_config',
   'telegram_bot_token', 'api_key', 'api_secret', 'sessdata']
  ```
- **无 `prompts_dir` 字段**. E92 实证:
  ```python
  c2 = Config()
  getattr(c2, 'prompts_dir', None)  → None
  'prompts_dir' in dir(c2)          → False
  ```
- `pipeline.py:150-157` 逻辑:
  ```python
  prompts_dir = getattr(ctx.config, "prompts_dir", None) if ctx.config else None
  custom_prompts = (
      Path(prompts_dir).expanduser()
      if isinstance(prompts_dir, str) and prompts_dir
      else None
  )
  ```
- 各类型行为:
  - `None` (real Config 或 mock spec 不含 prompts_dir) → `custom_prompts = None` → 走 builtin only
  - `""` (空字符串) → `isinstance str and prompts_dir` 第二项 falsy → `custom_prompts = None` → builtin
  - `"~/.builderpulse/prompts"` (非空 str) → `custom_prompts = Path(...).expanduser()` → 走 custom dir
  - `Path("/foo")` (Path 对象) → `isinstance(prompts_dir, str)` False → **`custom_prompts = None` 静默丢弃** ⚠️

**残余风险** (P2): 1 项 + 1 项 P3
- **R-V2-4 (P2)**: **生产 dead code**. `prompts_dir` 在 `Config` dataclass 中无字段. 整个 `custom_dir` lookup chain 在真实 production 路径上**永远走 builtin-only 分支** (因 `getattr(config, "prompts_dir", None)` 永远 None). 这意味着:
  1. 用户无法通过 `bp config set prompts_dir=...` 自定义 prompt (Config 无此字段)
  2. 用户无法通过 `BUILDERPULSE_PROMPTS_DIR` env var 自定义 (Config._apply_env_overrides 只看 dataclass fields)
  3. CLI / MCP / 配置文件 三个入口都**无法**注入 custom prompts_dir
  - 影响面: 本次 C1 唯一新增的 "custom override" 能力**事实上不可达**. 这不是 blocker (graceful fallback OK),但 R0 报告和 PR 描述说的 "custom > builtin > default" 3-tier 优先级 **只有 builtin + default-fallback 实际工作**.
  - 治本 (P1 级别修复): 在 `Config` dataclass 加 `prompts_dir: Optional[str] = None` 字段 + env override. 或者**文档明示** v2.2.0 builtin-only, custom override 留 v2.3.0.
  - **降级 P2 (而非 P1)**: 因为 builtin templates 已足够覆盖 5 大 source_type (bilibili/blogs/podcast/tweets + translate), 实际功能 **仍正常**; 问题只是 "用户扩展性" 缺失.
- **R-V2-5 (P3)**: Path-object 静默丢. 若未来有 caller 传 `Path` 对象 (e.g. 测试 helper / SDK user), `isinstance(prompts_dir, str)` 失败 → 走 builtin 不报错. **降级 P3**: silent fallback = 用户预期 (Path 是合理输入) ≠ 用户实际收到. 治本: 改 `isinstance(prompts_dir, (str, Path))` 或用 duck typing. 当前无 caller 触发, 待 v2.3.0 加 Config 字段时一并修.

### 风险 #4: CLI / MCP / config 一致性 — 三个入口行为是否一致

**评分**: P3 (low risk) 〔行为一致,因为 prompts_dir 永远是 None〕

**实证**:
- **CLI `bp process`** `cli.py:296-349`:
  - `cfg = Config(role_llm_model_map=role_llm_model_map) if role_llm_model_map else Config()` `cli.py:337`
  - 无 prompts_dir 注入 → step_summarize 走 builtin
  - **E92 实证**: end-to-end 跑 real Config + source_type='youtube' → `system=''` (无 youtube template,无 default), graceful fallback OK
- **MCP `_handle_process`** `mcp_server.py:351-396`:
  - `try: cfg = ConfigManager.get() except: cfg = Config()` `mcp_server.py:375-378`
  - `role_cfg = Config(role_llm_model_map=cfg_role_map) if cfg_role_map else Config()` `mcp_server.py:380`
  - 同样无 prompts_dir → 走 builtin
  - **行为与 CLI 一致** (因为 Config 永远无 prompts_dir 字段)
- **直接 `Pipeline.run()`** (测试 / 第三方):
  - `Pipeline(config=cfg)` → step_summarize 读 cfg.prompts_dir
  - Mock config 可任意塞 prompts_dir, 真实 Config 永远 None

**残余风险** (P3): 1 项
- **R-V2-6 (P3)**: 三个入口的行为**事实上**完全一致, 因为 prompts_dir 不可注入. 一致性风险是 *负面的* 一致 — 用户无论用哪个入口都无法触发 custom override. 等同于 R-V2-4 的副作用, 不重复升 severity. **降级 P3**: R-V2-4 治本后此风险自然消失.

### 风险 #5: 下游影响 — 旧测试 `Mock(model="gpt-4")` 无 prompts_dir 是否仍能 fallback 到空 system

**评分**: P3 (low risk) 〔完整验证 pass〕

**实证**:
- E92 实证 (R-V2-1 复用):
  ```python
  src = SourceRef(source_type='youtube', native_id='t', url='https://x')
  ctx = PipelineContext(source=src, config=Mock(model='gpt-4', api_key='test', language='zh'))
  ctx.transcript = type('T', (), {'text': 'content' * 50})()
  with patch('builderpulse.remix.summarizer.get_provider') as mp:
      m = mp.return_value
      m.complete.return_value = 'OK'
      ctx = step_summarize(ctx)
  print('summary:', ctx.summary)  → 'OK'
  print('errors:', ctx.errors)    → []
  ```
- 系统消息: `system=''` 传给 `provider.complete('content...', system='')` (E92 实证 call_args 输出)
- `Summarizer.summarize(text, system='')` E92 实证:
  ```
  out: OK
  call_args: call('hello', system='')
  ```
- AnthropicProvider 内置 fallback: `system=system or "You are a helpful assistant."` `summarizer.py:59` — 旧 v2.1.0 行为保留
- OpenAIProvider 走 `if system: messages.append(...)` `summarizer.py:31-32` — 空 system 不附加 system message, 等同 v2.1.0
- OllamaProvider 走 `if system: payload["system"] = system` `summarizer.py:79-80` — 同样不附加

**回归套件实证** (E92):
```
tests/test_pipeline.py + tests/test_pipeline_remix.py + tests/test_prompt_registry.py:
22 passed in 0.19s

core integration (pipeline + remix + prompt_registry + mcp + cli + remix):
55 passed in 25.80s
```
R0 报告的 "609 regression pass" 我未在本 session 全跑 (test_performance 跑 background, 25s 已知), 但核心 5 套件 55/55 实证 pass.

**残余风险** (P3): 1 项
- **R-V2-7 (P3)**: `hasattr(ctx.config, "role_llm_registry")` 在 mock config 上表现 "正确但 fragile" (R-V2-1 副作用). mock object 默认返回 truthy Mock 实例 — 走 `get_role_provider` 分支,实际测试通过, 但生产 Config 无 `role_llm_registry` attribute (是 `@property` 懒构造) → `hasattr` True 但走 `role_llm_registry` → 构造新 registry → 内部仍调 `get_provider` (被 @patch 截). 实际行为正确, 但 mock vs real 的语义有微妙差异. **降级 P3**: 旧测试套件已 pass, 无新风险.

---

## 3. 验证: 已跑命令 + 输出

### 3.1 新代码 16/16 测试

```bash
$ cd "D:/Claude Code/workspace/projects/builderpulse"
$ python -m pytest tests/test_prompt_registry.py tests/test_pipeline_remix.py -v

============================= 16 passed in 0.14s ==============================
```

### 3.2 核心回归 55/55

```bash
$ python -m pytest tests/test_pipeline.py tests/test_pipeline_remix.py \
    tests/test_prompt_registry.py tests/test_mcp_handlers.py \
    tests/test_cli.py tests/test_remix.py -q

.......................................................                  [100%]
55 passed in 25.80s
```

### 3.3 End-to-end 实证 (real Config, source_type='youtube')

```python
src = SourceRef(source_type='youtube', native_id='test', url='https://x')
ctx = PipelineContext(source=src, config=Config())
ctx.transcript = Mock(text='hello world' * 100)
with patch('builderpulse.remix.summarizer.get_provider') as mp:
    m = mp.return_value
    m.complete.return_value = 'OK'
    ctx = step_summarize(ctx)

# call_args: call('hello world...', system='')
# summary: OK
# errors: []
```

### 3.4 Backward compat (旧 Mock 模式)

```python
ctx = PipelineContext(source=src, config=Mock(model='gpt-4', api_key='test', language='zh'))
# 5 runs in a row: all 5 returns distinct OK
```

---

## 4. 0 finding 时必写 Residual Risks (H45 item 13)

> H44 宪法 §0.2: "0 finding 必写 N residual risk, 不写 PASS"
> 0 finding 仍然 8 项 residual risk 实证列出 (P2 / P3, 无 P0/P1)

| ID | Severity | 类别 | 描述 | 触发条件 | 治本建议 |
|:---|:---------|:-----|:-----|:---------|:---------|
| **R-V2-1** | P3 | Signature | Mock config 缺 `role_llm_registry` 时, `hasattr` 返回 truthy → 走 Role 分支 (语义 fragile 但行为正确) | 单测 / 第三方 SDK 用 Mock() 而非 spec= | 文档化; 或用 `getattr(config, 'role_llm_registry', None)` |
| **R-V2-2** | P3 | 死代码 | `RolePromptRegistry.warm()` 公开 API, 生产 0 调用 | 大批量 source_type 场景理论可提速 | v2.3.0 加 startup warm 钩子 |
| **R-V2-3** | P3 | Cache staleness | 模板运行时修改不被 cache 感知 | 长期 daemon + 文件 in-place edit | 加 mtime 校验; 短期不修 |
| **R-V2-4** | **P2** | **生产死代码** | `prompts_dir` **不在** `Config` dataclass 字段列表. `getattr(config, 'prompts_dir', None)` 永远 None. 整个 `custom_dir` 路径在 production 不可达. 用户无法通过 `bp config set` / `BUILDERPULSE_PROMPTS_DIR` 自定义 prompt. | 任何 production 调用 (CLI/MCP/direct Pipeline.run) | **修**: `Config` 加 `prompts_dir: Optional[str] = None` 字段 + `_apply_env_overrides` 自动捕获. 或**文档明示 v2.2.0 builtin-only** |
| **R-V2-5** | P3 | 静默 fallback | `isinstance(prompts_dir, str)` 拒收 `Path` 对象. 静默走 builtin. | 测试 / SDK caller 传 `Path` 对象 | 改 `isinstance(prompts_dir, (str, Path))` |
| **R-V2-6** | P3 | 一致性副作用 | CLI/MCP/direct 三个入口行为**事实上完全一致** = 都用 builtin. R-V2-4 治本后此风险自然消失 | R-V2-4 修复后评估 | 与 R-V2-4 同步 |
| **R-V2-7** | P3 | Mock fragile | `hasattr(ctx.config, "role_llm_registry")` 在 mock vs real Config 上语义有微妙差异 (mock 默认 truthy, real 是 @property) | 单测环境 | spec= 限定 Mock 接口 |
| **R-V2-8** | P3 | R0 报告 stale | R0-self-check.md 提到 "Working Tree 污染 12 modified + 5 untracked", `git status` 状态. 本审计未在 R1a V2 范围核查. | commit 决策前需 user 拍板 (R0 已 BLOCK on user decision) | 不在 R1a V2 scope; 留 C1.3 review 路径处理 |

---

## 5. 关键发现总结 (1 句话版)

**5 类风险中 4 类为 P3, 1 类为 P2**: `prompts_dir` 字段未在 `Config` dataclass 声明, 整个 custom override 路径在 production 不可达 (R-V2-4). 16/16 新测试 pass, 55/55 核心回归 pass, 端到端 graceful fallback 完整工作 (real Config + 无 template → system='' → LLM 用 provider default). Backward compat 完整保留. **无 P0/P1 阻断**, 但 P2 R-V2-4 建议在 commit 决策时讨论 (要么加 Config 字段,要么文档明示 builtin-only).

---

## 6. 决策选项 (per H49 User-Decision-Required, 12 次 user push back 实证)

R-V2-4 (P2) 触发, 3 选项待 user 拍板:

| 选项 | 描述 | 影响面 | 风险 |
|:-----|:-----|:-------|:-----|
| **A. 接受 dead code, 文档明示** | v2.2.0 builtin-only, custom override 留 v2.3.0 PR | 小 (1 行 doc + CHANGELOG note) | 零 |
| **B. 在 Config 加 prompts_dir 字段** | `Config` dataclass + env override + ConfigManager 持久化 | 中 (~30 行 + 测试) | 需重跑回归; 文档说明 |
| **C. 接受现状, 不文档化** | v2.2.0 直接 commit | 零 | 用户读到 R0/R1a 报告后困惑 |

**推荐**: A (最小变更, 治本留 v2.3.0). H49 兜底: 不可自决, 等 user 拍板.

---

## 7. H44 R3 self-disclosure

- 不写 PASS / 完成 / 闭环. 数据 + 实证 + residual 列表呈现.
- 1 P2 finding (R-V2-4) 必走 user 拍板, 不在本审计 scope 内自决.
- 7 P3 finding 全部降级 (by design / mock 环境 / 死代码 / 文档未到位), 不阻塞.
- 全程未修改任何文件 (audit only per task description).
- 5 类风险逐项 E92 实证 (cache 线程安全 / cache staleness / real Config 字段列表 / end-to-end / 5 连续 run 状态隔离).
- 完整调用链 6 步绘制 (URL → Pipeline.run → step_summarize → RolePromptRegistry.get → Summarizer.summarize → AnthropicProvider.complete).
- 0 finding 必写 8 项 residual risks (H45 item 13 + §0.2 宪法强制).

---

**报告版本**: v1 (2026-06-26 inline)
**审计员**: H44 R1a V2 Verifier (集成正确性专项)
**下一步**: C1.3 5 轮 review 路径 (R1a V1 测试覆盖 + R1a V3 生产就绪度 + R1b 对抗性 + R2 独立审计), R1a V2 本份即 R3 residual disclosure 闭环.
