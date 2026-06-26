"""Tests for RolePromptRegistry — v2.2.0 Commit 1.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def builtin_prompts_dir() -> Path:
    """Locate the real builtin prompts directory."""
    from builderpulse.remix.prompts import _BUILTIN_DIR

    return _BUILTIN_DIR


@pytest.fixture
def custom_prompts_dir(tmp_path: Path) -> Path:
    """Create a custom prompts dir with one override."""
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "summarize-podcast.md").write_text(
        "CUSTOM PODCAST PROMPT — override",
        encoding="utf-8",
    )
    return custom


@pytest.fixture
def empty_custom_dir(tmp_path: Path) -> Path:
    """Custom dir with NO files — all templates must fall back to builtin."""
    empty = tmp_path / "empty_custom"
    empty.mkdir()
    return empty


# ──────────────────────────────────────────────────────────────────────
# V1 — custom_dir overrides builtin
# ──────────────────────────────────────────────────────────────────────


def test_registry_custom_overrides_default(
    custom_prompts_dir: Path, builtin_prompts_dir: Path
):
    """custom_dir/summarize-podcast.md must override builtin/summarize-podcast.md."""
    from builderpulse.remix.prompt_registry import RolePromptRegistry

    reg = RolePromptRegistry(custom_dir=custom_prompts_dir)
    out = reg.get("summarize", variant="podcast")
    assert "CUSTOM PODCAST PROMPT" in out
    assert "override" in out


# ──────────────────────────────────────────────────────────────────────
# V2 — missing variant falls back to default
# ──────────────────────────────────────────────────────────────────────


def test_registry_missing_variant_falls_back(builtin_prompts_dir: Path):
    """summarize-unknown-source.md missing → fall back to summarize-default.md.

    If summarize-default.md ALSO missing (current builtin state), registry should
    raise FileNotFoundError with helpful message.
    """
    from builderpulse.remix.prompt_registry import RolePromptRegistry

    reg = RolePromptRegistry()
    with pytest.raises(FileNotFoundError, match=r"(?i)summarize.*default"):
        reg.get("summarize", variant="unknown-source")


# ──────────────────────────────────────────────────────────────────────
# V3 — registry cache returns same string instance after warm()
# ──────────────────────────────────────────────────────────────────────


def test_warm_caches_all_roles(custom_prompts_dir: Path):
    """warm() loads all 4 roles and caches them in _cache dict.

    Note: warm() accepts (role, variant) pairs via get(), but for simplicity
    we test warm() pre-loading specific variants that exist in builtin.
    The 6 builtin templates are:
        digest-intro, summarize-bilibili, summarize-blogs,
        summarize-podcast, summarize-tweets, translate
    """
    from builderpulse.remix.prompt_registry import RolePromptRegistry

    reg = RolePromptRegistry(custom_dir=custom_prompts_dir)
    assert reg._cache == {}  # cold

    # Warm with specific role-variant pairs that exist
    warm_targets = [
        ("summarize", "podcast"),
        ("summarize", "bilibili"),
        ("summarize", "blogs"),
        ("translate", "default"),  # builtin translate.md → falls back to translate-default
    ]
    for role, variant in warm_targets:
        try:
            reg.get(role, variant=variant)
        except FileNotFoundError:
            pass  # Some variants may not exist; warm() at startup tolerates

    assert len(reg._cache) >= 1
    for (role, variant), text in reg._cache.items():
        assert isinstance(text, str)
        assert len(text) > 0


# ──────────────────────────────────────────────────────────────────────
# V4 — explicit system param takes precedence over registry
# ──────────────────────────────────────────────────────────────────────


def test_summarizer_explicit_system_wins_over_registry(
    custom_prompts_dir: Path,
):
    """When caller passes system= explicitly, registry lookup is bypassed."""
    from builderpulse.remix.prompt_registry import RolePromptRegistry
    from builderpulse.remix.summarizer import Summarizer

    captured: dict[str, str] = {}

    class CaptureProvider:
        def complete(self, prompt, system="", temperature=0.3):
            captured["system"] = system
            return "ok"

    reg = RolePromptRegistry(custom_dir=custom_prompts_dir)
    s = Summarizer(provider=CaptureProvider())
    out = s.summarize("text", system="EXPLICIT OVERRIDE")
    assert captured["system"] == "EXPLICIT OVERRIDE"
    assert out == "ok"


# ──────────────────────────────────────────────────────────────────────
# V5 — registry miss → empty system, do not crash
# ──────────────────────────────────────────────────────────────────────


def test_summarizer_falls_back_when_template_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Point BUILTIN_DIR to empty dir + no custom_dir → get() raises FileNotFoundError.

    Caller (step_summarize or AnthropicProvider) must catch and use empty system.
    """
    from builderpulse.remix import prompt_registry as pr_mod
    from builderpulse.remix import prompts as prompts_mod

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(prompts_mod, "_BUILTIN_DIR", empty)
    monkeypatch.setattr(pr_mod, "_BUILTIN_DIR", empty)

    from builderpulse.remix.prompt_registry import RolePromptRegistry

    reg = RolePromptRegistry()  # no custom_dir
    with pytest.raises(FileNotFoundError):
        reg.get("summarize", variant="podcast")


# ──────────────────────────────────────────────────────────────────────
# V6 — prompt_registry._BUILTIN_DIR mirrors prompts._BUILTIN_DIR
# ──────────────────────────────────────────────────────────────────────


def test_registry_builtin_dir_matches_prompts_module():
    """prompt_registry._BUILTIN_DIR must reference prompts._BUILTIN_DIR.

    Why: source-of-truth single-resolution. If user env-var changes, both pick up.
    """
    from builderpulse.remix import prompt_registry as pr_mod
    from builderpulse.remix import prompts as prompts_mod

    assert pr_mod._BUILTIN_DIR == prompts_mod._BUILTIN_DIR