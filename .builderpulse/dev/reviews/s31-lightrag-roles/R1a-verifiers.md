# R1a — 3 Verifier 交叉验证报告 (Session 31)

> **范围**: Session 31 M1 (Role 抽象) + M2 (Source Aggregator 重构)
> **方法**: 3 independent subagent 并行验证 (互不通信)
> **H45 item 13**: 不写 PASS verdict

## Verifier 矩阵

| Verifier | 焦点 | 主要 finding | 一句话总结 |
|:--|:--|:--|:--|
| **V1** (测试覆盖) | 单测覆盖度 / mock | P0-1/2/3 (核心模块 0 单测) | 146 行 roles.py + 重构的 aggregator 0 直接单测 |
| **V2** (集成正确性) | 调用链 / signature / 状态污染 | P0 R-P0-1 (register_all 全局污染) | register_all 通过 alias 改 DEFAULT_ROLE_SPECS, Python REPL 已实证 |
| **V3** (生产就绪度) | 部署 / 配置 / 文档 / 可观测 | P0-CFG-1 (docker-compose Windows path) | docker-compose.yml line 15 hardcoded Windows path, Linux/macOS 直接 break |

**3/3 一致**: 全部发现 P0 阻断（虽然不同维度）

## P0 阻塞项（必须修）

### P0-A: docker-compose.yml Windows hardcoded path (V3)

**位置**: `docker-compose.yml:15`

```yaml
volumes:
  - C:/Users/12739/.builderpulse:/root/.builderpulse:ro  # ← hardcoded!
```

**影响**: Linux/macOS 上 `docker compose up` 路径不存在 → 静默挂错路径或报错

**修复**（V3 给出方案）:
```yaml
volumes:
  - ${HOST_BUILDERPULSE_DIR:-${HOME}/.builderpulse}:/root/.builderpulse:ro
```

**修复成本**: 1 行

---

### P0-B: RoleLLMRegistry.register_all 通过 alias 改全局 DEFAULT_ROLE_SPECS (V2)

**位置**: `roles.py:109-111`

```python
def register_all(self, model_map):
    for role_name, model in model_map.items():
        try:
            role = Role(role_name)
        except ValueError:
            continue
        spec = self.get_spec(role)          # ← 返回 DEFAULT_ROLE_SPECS 里的同引用
        spec.model = model                  # ← MUTATES 全局模块级 dict
        self._specs[role] = spec
```

**触发链**:
1. `__init__(specs=None)` 走 `specs or dict(DEFAULT_ROLE_SPECS)` (line 90)
2. `dict(DEFAULT_ROLE_SPECS)` 是 shallow copy — dict 是新对象，**但内部 RoleSpec 仍是 DEFAULT 引用**
3. `get_spec(role)` 命中 `self._specs[role]` → 拿 DEFAULT 引用
4. `spec.model = model` → **改全局 module state**

**Python REPL 实证** (V2 已跑):
```
rmod.DEFAULT_ROLE_SPECS[Role.EXTRACT].model = "auto"
r = rmod.RoleLLMRegistry()
r.register_all({"extract": "INJECTED"})
rmod.DEFAULT_ROLE_SPECS[Role.EXTRACT].model == "INJECTED"  # True
```

**影响**: CLI `process --role-model extract=X` 跑一次 → 后续 `Config()` 静默用 X 而非 "auto" → 多用户/长跑 MCP server 状态污染

**修复**（V2 给出方案）:
```python
import copy

class RoleLLMRegistry:
    def __init__(self, specs=None):
        if specs is None:
            # 治本：deep copy 避免共享 RoleSpec 引用
            self._specs = {
                role: copy.deepcopy(spec)
                for role, spec in DEFAULT_ROLE_SPECS.items()
            }
        else:
            self._specs = specs
```

**修复成本**: 3 行（加 import + 改 __init__）

---

### P0-C: S31 新核心模块 0 直接单测 (V1)

**影响**: 22 个新 API 元素 (roles.py 11 + source_aggregator.py 11) 0 直接单测，仅靠间接集成测试

**修复建议** (V1 给出):
- 新建 `tests/test_remix_roles.py` (~150 行): Role enum 4 值 / RoleLLMRegistry 默认 4 spec / `register_all` 含未知 role 跳过 / `to_dict` mask api_key / `from_dict` 解 "***" / `get_spec` 已知未知路径 / `get_role_provider` 透传
- 新建 `tests/test_source_aggregator.py` (~120 行): `_normalise_sources` 5 分支 / `fetch_all_sources` 注册表循环 / 5 fetcher 各 mock / `register_source` 重名 / `list_sources` / `_safe_fetch` raise 路径
- `test_pipeline_remix.py` 加 2 个 happy path: `step_summarize` 走 Role.EXTRACT + `step_translate` 走 Role.TRANSLATE

**修复成本**: ~270 行新测试

**本 review 处理决策**: 
- ✅ 修 P0-A（1 行 docker-compose 改动）
- ✅ 修 P0-B（3 行 RoleLLMRegistry deepcopy）
- ⚠️ **P0-C 由 Session 31 commit 负责人补**（不是 v2.2.0 C1 范围；本 review 只 flag 不补）

## P1 列表（合并 3 verifier）

| ID | 来源 | 描述 | 阻塞 |
|:--|:--|:--|:--|
| P1-1 | V2 | `step_summarize`/`step_translate` 兜底分支死代码（role_llm_registry 永真） | 否 |
| P1-2 | V2 | CLI 临时 Config vs MCP 持久 Config 行为分叉 | 否 |
| P1-3 | V2 | `from_dict` 把 `api_key == "***"` 当 mask 解码 | 否 |
| P1-4 | V3 | Dockerfile aliyun mirror 假设（国际用户慢） | 否 |
| P1-5 | V3 | healthcheck 太弱（`import builderpulse` 不代表 MCP 健康） | 否 |
| P1-6 | V3 | README 测试数 449→609 stale + RoleLLMRegistry Public API 文档缺失 | 否 |
| P1-7 | V3 | roles.py 整文件无 logger | 否 |
| P1-8 | V3 | anthropic>=0.20 缺 upper-bound（SDK 1.0 风险） | 否 |
| P1-9 | V1 | cli `--role-model` 无 happy path + 格式错路径未测 | 否 |

**P1 处理**: 9 项全部留 backlog，不阻塞本 review 推进；CHANGELOG 中标注"9 P1 待下个版本"

## P2 列表（合并 3 verifier, 9 项）

| ID | 来源 | 描述 |
|:--|:--|:--|
| P2-1 | V1 | empty `_FETCHERS` 行为未测 |
| P2-2 | V1 | `_safe_fetch` raise 路径未测 |
| P2-3 | V2 | `_FETCHERS` vs `_VALID_SOURCES` 紧约束 trap |
| P2-4 | V2 | `_normalise_sources` 静默丢弃未知 source |
| P2-5 | V2 | R-P3-3 MCP `bp_process` try/except 静默吞所有异常 |
| P2-6 | V2 | `--role-model` 无 schema 验证 |
| P2-7 | V3 | `config.example.json` 缺 `role_llm_model_map` 示例 |
| P2-8 | V3 | `Config.from_file` 缺 unknown-key warning |
| P2-9 | V3 | source_aggregator 无 logger |

**P2 处理**: 全部 backlog

## OK 列表（合并 3 verifier, 共识）

- ✅ 现有 609 tests pass + 4 skipped（166s 跑完）
- ✅ 0 breaking change 旧 API
- ✅ step_download / cli process / cli digest / cli fetch / cli transcribe / MCP bp_* 全 backward compatible
- ✅ `_FETCHERS` 空字典行为正常（V3 实证）
- ✅ `register_all` invalid role silently skip（V3 实证）
- ✅ `step_summarize` prompts graceful degradation（C1 + S31 联动）
- ✅ `RoleLLMRegistry.to_dict()` api_key `"***"` mask
- ✅ `.gitignore` H17 v3 + H32 集中式 .bak 协议落地
- ✅ Dockerfile 双 stage + tini PID 1
- ✅ `__init__.py` 导出 4 个新符号
- ✅ 所有 Public API 有 docstring
- ✅ MCP `_handle_process` 走 ConfigManager.role_llm_model_map
- ✅ pyproject.toml 无新依赖引入
- ✅ 所有新函数 CC < 10

## 3/3 共识判定

3 verifier 全部发现 P0 → **必修 P0-A + P0-B 后进 R1b**（adversarial）

P0-C 由 Session 31 commit 负责人补，不阻塞 R1b 推进。

## 已采取行动（写本报告时同步修）

- [x] **P0-A (docker-compose)**: 改 `${HOST_BUILDERPULSE_DIR:-${HOME}/.builderpulse}` env var 化（已修）
- [x] **P0-B (register_all 污染)**: `__init__` 改 `copy.deepcopy(DEFAULT_ROLE_SPECS)`（已修 + REPL 实证）

### P0-B 修复实证

```python
# REPL 输出:
BEFORE: DEFAULT_ROLE_SPECS[EXTRACT].model = auto
r = RoleLLMRegistry()
r.register_all({"extract": "INJECTED", "unknown_role": "skip"})
AFTER:  DEFAULT_ROLE_SPECS[EXTRACT].model = auto        ← 全局未被污染 ✓
r._specs[EXTRACT].model = INJECTED                       ← 局部正确注入 ✓
污染测试: True
局部注入测试: True
```

- [ ] P0-C（测试覆盖）: flag 不修，留 S31 owner backlog