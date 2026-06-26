"""RolePromptRegistry — central prompt template lookup with role × variant dimension.

v2.2.0 Commit 1: 取代 step_summarize 中散落的 system= "" 调用,
通过 role × variant 二维坐标统一加载 .md 模板。

Usage:
    reg = RolePromptRegistry(custom_dir=Path("~/.builderpulse/prompts"))
    system = reg.get("summarize", variant=ctx.source.source_type)  # → "summarize-podcast.md"
    out = provider.complete(prompt, system=system)

Priority:
    1. custom_dir/<role>-<variant>.md (if exists)
    2. builtin _BUILTIN_DIR/<role>-<variant>.md (if exists)
    3. custom_dir/<role>-default.md (fallback)
    4. builtin _BUILTIN_DIR/<role>-default.md (fallback)
    5. raise FileNotFoundError

Thread safety: _cache dict is read-only after warm() finishes; warm() is not
thread-safe by design — call once at startup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from builderpulse.remix.prompts import _BUILTIN_DIR as _PROMPTS_BUILTIN_DIR

logger = logging.getLogger("builderpulse.remix.prompt_registry")

# Re-export for tests that monkeypatch this module's _BUILTIN_DIR
_BUILTIN_DIR: Path = _PROMPTS_BUILTIN_DIR


class RolePromptRegistry:
    """Look up prompt templates by (role, variant).

    The role is the *function* (e.g. "summarize", "translate", "extract"),
    the variant is the *content type* (e.g. "podcast", "bilibili", "blog").

    Template filename pattern: ``<role>-<variant>.md``.
    """

    def __init__(self, custom_dir: Path | None = None):
        self._custom_dir = Path(custom_dir).expanduser() if custom_dir else None
        self._cache: dict[tuple[str, str], str] = {}

    def get(self, role: str, variant: str = "default") -> str:
        """Return prompt text for (role, variant).

        Raises FileNotFoundError if neither custom nor builtin has the file
        AND no ``<role>-default.md`` fallback exists.
        """
        key = (role, variant)
        if key in self._cache:
            return self._cache[key]

        # 1. custom_dir/<role>-<variant>.md
        if self._custom_dir is not None:
            custom_path = self._custom_dir / f"{role}-{variant}.md"
            if custom_path.exists():
                text = custom_path.read_text(encoding="utf-8")
                self._cache[key] = text
                logger.debug("prompt registry: custom %s/%s hit", role, variant)
                return text

        # 2. builtin/<role>-<variant>.md
        builtin_path = _BUILTIN_DIR / f"{role}-{variant}.md"
        if builtin_path.exists():
            text = builtin_path.read_text(encoding="utf-8")
            self._cache[key] = text
            logger.debug("prompt registry: builtin %s/%s hit", role, variant)
            return text

        # 3. fallback to <role>-default.md (same lookup chain)
        if variant != "default":
            return self.get(role, variant="default")

        # 4. exhausted
        raise FileNotFoundError(
            f"Prompt template not found: {role}-{variant}.md "
            f"(searched: custom={self._custom_dir}, builtin={_BUILTIN_DIR})"
        )

    def warm(self, roles: Iterable[str]) -> None:
        """Pre-load templates for the given roles into cache.

        For each role, attempts to load ``<role>-default.md``.
        Missing templates are silently skipped (logged at DEBUG).
        """
        for role in roles:
            try:
                self.get(role, variant="default")
            except FileNotFoundError:
                logger.debug(
                    "prompt registry warm: %s-default.md not found, skipping", role
                )