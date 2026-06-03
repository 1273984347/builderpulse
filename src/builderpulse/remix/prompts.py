"""Prompt template loader with custom > builtin priority."""
from __future__ import annotations
from pathlib import Path

_BUILTIN_DIR = Path(__file__).parent.parent / "prompts"  # inside the package

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
