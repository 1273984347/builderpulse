"""Role-specific LLM abstraction — Session 31 M1 派生 from LightRAG llm_roles.py.

跟 LightRAG 4 角色 (EXTRACT/QUERY/KEYWORDS/VLM) 同源,适配 BuilderPulse 实际:
- EXTRACT    — step_summarize (深度摘要, 30B 模型推荐, 需强推理)
- QUERY      — 用户查询回答 (长上下文, 待 step_query 实现)
- KEYWORDS   — 关键词抽取 (轻量, 8B 即可, 待实现)
- TRANSLATE  — step_translate (轻量翻译, 8B 即可, 跟 EXTRACT 并行)

设计原则:
- 4 角色独立 model, 避免"5 阶段硬塞同一 LLM"反模式
- 跟 LightRAG 同样的 RoleSpec 数据类 + 注册表模式
- 单一 LLM 路径仍可走 get_provider() (向后兼容)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Role(str, Enum):
    """4 角色 LLM — 跟 LightRAG EXTRACT/QUERY/KEYWORDS/VLM 范式对齐."""

    EXTRACT = "extract"      # 深度摘要 / 实体-关系抽取
    QUERY = "query"          # 用户查询 / 跨文档推理
    KEYWORDS = "keywords"    # 关键词抽取 / 轻量任务
    TRANSLATE = "translate"  # 翻译 / 轻量并行


@dataclass
class RoleSpec:
    """单角色 LLM 配置 — 跟 LightRAG RoleSpec 同结构."""

    name: str
    model: str = "auto"           # model name; "auto" 走 get_provider() 默认
    api_key: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoleSpec":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Default specs — 各角色合理默认 (跟 LightRAG 默认类似)
DEFAULT_ROLE_SPECS: dict[Role, RoleSpec] = {
    Role.EXTRACT: RoleSpec(
        name="extract",
        model="auto",  # 走 get_provider("auto") — 强推理 LLM (claude-sonnet / gpt-4o)
        temperature=0.3,
        max_tokens=4096,
        description="深度摘要 / 实体-关系抽取 — 需 30B+ 强推理 LLM",
    ),
    Role.QUERY: RoleSpec(
        name="query",
        model="auto",
        temperature=0.5,
        max_tokens=8192,
        description="用户查询 / 跨文档推理 — 需长上下文 LLM",
    ),
    Role.KEYWORDS: RoleSpec(
        name="keywords",
        model="auto",
        temperature=0.2,
        max_tokens=1024,
        description="关键词抽取 — 8B 轻量 LLM 即可",
    ),
    Role.TRANSLATE: RoleSpec(
        name="translate",
        model="auto",  # 走 get_provider() 默认 — 8B 轻量 LLM
        temperature=0.1,  # 翻译要确定性, 温度低
        max_tokens=8192,
        description="翻译 — 8B 轻量 LLM 即可, 跟 EXTRACT 并行",
    ),
}


class RoleLLMRegistry:
    """注册表 — 跟 LightRAG ROLES 模式同源.

    单一实例 per Config, 通过 ctx.config.role_registry 传递到 pipeline.
    """

    def __init__(self, specs: dict[Role, RoleSpec] | None = None):
        if specs is None:
            # 治本 (R1a P0-B + R1b B-2/B-3): deep copy 避免共享 DEFAULT_ROLE_SPECS 里的 RoleSpec 引用
            # 否则 register_all() 通过 spec.model = model 会污染全局 module state
            self._specs = {
                role: copy.deepcopy(spec)
                for role, spec in DEFAULT_ROLE_SPECS.items()
            }
        else:
            # 治本 (R1b B-3): caller 传 dict 时也 deep copy, 防止外部 alias 污染
            self._specs = {
                role: copy.deepcopy(spec) for role, spec in specs.items()
            }

    def get_spec(self, role: Role) -> RoleSpec:
        """拿某角色 spec, 不存在则用 default."""
        if role in self._specs:
            return self._specs[role]
        # 治本 (R1b B-4): fallback 也 deep copy, 防止 caller 修改返回 spec 污染全局
        return copy.deepcopy(DEFAULT_ROLE_SPECS[role])

    def register(self, role: Role, spec: RoleSpec) -> None:
        """覆盖某角色 spec (CLI / env / config 入口)."""
        # 治本 (R1b B-2): caller 传入 spec 也 deep copy, 防止 caller 后续修改污染 registry
        self._specs[role] = copy.deepcopy(spec)

    def register_all(self, model_map: dict[str, str]) -> None:
        """批量 register (从 config 加载). model_map: {"extract": "claude-opus-4", "translate": "ollama/llama3"}."""
        for role_name, model in model_map.items():
            try:
                role = Role(role_name)
            except ValueError:
                continue  # 跳过未知 role, 不报错
            spec = self.get_spec(role)
            spec.model = model
            self._specs[role] = spec

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """导出 (config 持久化 / API 输出). 隐藏 api_key."""
        return {
            role.value: {
                **spec.to_dict(),
                "api_key": "***" if spec.api_key else None,  # 敏感字段 mask
            }
            for role, spec in self._specs.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, Any]]) -> "RoleLLMRegistry":
        specs = {}
        for role_name, spec_data in data.items():
            try:
                role = Role(role_name)
            except ValueError:
                continue
            # 跳过 masked api_key
            if spec_data.get("api_key") == "***":
                spec_data = {**spec_data, "api_key": None}
            specs[role] = RoleSpec.from_dict(spec_data)
        return cls(specs)


def get_role_provider(role: Role, registry: RoleLLMRegistry):
    """拿某角色对应的 LLMProvider — 跟 lightrag/llm.py::get_role_llm 同源.

    透传 spec 给 get_provider, 避免重复实现 provider 选择.
    """
    from .summarizer import get_provider  # 避免循环 import

    spec = registry.get_spec(role)
    return get_provider(model=spec.model, api_key=spec.api_key)
