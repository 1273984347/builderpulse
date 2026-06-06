"""Prompt template loader with custom > builtin priority."""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path


def _find_builtin_prompts() -> Path:
    """Locate the built-in prompts directory.

    Resolution order:
        1. importlib.resources (works in zip/wheel installs)
        2. Walk up __file__ parents until a prompts/ dir with *.md is found
        3. BUILDERPULSE_PROMPTS_PATH env var
        4. FileNotFoundError with helpful message
    """
    # 1. Try importlib.resources
    try:
        ref = importlib.resources.files("builderpulse") / "prompts"
        # If it resolves to a real directory, use it
        resolved = Path(str(ref))
        if resolved.is_dir() and any(resolved.glob("*.md")):
            return resolved
    except (TypeError, ModuleNotFoundError, FileNotFoundError):
        pass

    # 2. Walk up __file__ parents
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "prompts"
        if candidate.is_dir() and any(candidate.glob("*.md")):
            return candidate

    # 3. Env var fallback
    env_path = os.environ.get("BUILDERPULSE_PROMPTS_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_dir() and any(p.glob("*.md")):
            return p

    # 4. Give up
    raise FileNotFoundError(
        "Cannot locate built-in prompts directory. "
        "Set BUILDERPULSE_PROMPTS_PATH env var to the prompts/ folder, "
        "or ensure the 'prompts' directory exists next to the builderpulse package."
    )


_BUILTIN_DIR = _find_builtin_prompts()


def load_prompt(name: str, custom_dir: str | Path | None = None) -> str:
    """Load a prompt template. Custom dir overrides builtin."""
    if custom_dir:
        custom_path = Path(custom_dir) / f"{name}.md"
        if custom_path.exists():
            return custom_path.read_text(encoding="utf-8")

    builtin_path = _BUILTIN_DIR / f"{name}.md"
    if builtin_path.exists():
        return builtin_path.read_text(encoding="utf-8")

    raise FileNotFoundError(f"Prompt template not found: {name}")


def list_prompts(custom_dir: str | Path | None = None) -> list[str]:
    """List available prompt names."""
    names = set()
    if _BUILTIN_DIR.exists():
        names.update(p.stem for p in _BUILTIN_DIR.glob("*.md"))
    if custom_dir:
        custom_path = Path(custom_dir)
        if custom_path.exists():
            names.update(p.stem for p in custom_path.glob("*.md"))
    return sorted(names)
