"""Test that bilingual READMEs don't drift apart.

Ref: spec §3.2 step 6 (CI 校验) + §6.2 (错误码 BP_I18N_DRIFT).
This test guards against silent drift between the English and Chinese
READMEs — adding a section to one without the other will fail CI.

TODO: Re-add "Docker" to REQUIRED_KEYWORDS_EN/ZH after T4 (Dockerfile
creation) lands. Currently dropped because READMEs don't reference
Docker yet — that is a T4 deliverable, not a T3 concern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from builderpulse.core.error_codes import ErrorCode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README_ZH = PROJECT_ROOT / "README.zh-CN.md"
README_EN = PROJECT_ROOT / "README.md"

# Key keywords that must appear in both READMEs (spec §3 关键决策).
# Docker is intentionally absent — T4 (Dockerfile integration) will
# add a "## Docker" section to both READMEs; re-add it here at that time.
REQUIRED_KEYWORDS_EN = ["Installation", "Quick Start", "Configuration", "MCP"]
REQUIRED_KEYWORDS_ZH = ["安装", "快速开始", "配置", "MCP"]


def _extract_h2_sections(readme: Path) -> list[str]:
    """Extract H2 section titles (## X) from a markdown file."""
    return re.findall(r"^##\s+(.+)$", readme.read_text(encoding="utf-8"), re.MULTILINE)


def test_readme_files_exist() -> None:
    """Both bilingual READMEs must exist."""
    assert README_ZH.exists(), f"Missing bilingual README: {README_ZH}"
    assert README_EN.exists(), f"Missing bilingual README: {README_EN}"


def test_bilingual_h2_count_match() -> None:
    """H2 section count must match (drift detection).

    If you add a new top-level section to one README, you must add the
    bilingual equivalent to the other. Run i18n sync before committing.
    """
    zh = _extract_h2_sections(README_ZH)
    en = _extract_h2_sections(README_EN)
    assert len(zh) == len(en), (
        f"i18n drift: README.zh-CN.md has {len(zh)} H2 sections, "
        f"README.md has {len(en)}. Bilingual READMEs must stay in sync."
    )


def test_required_keywords_en() -> None:
    """English README must contain all required keywords (drift detection)."""
    en_text = README_EN.read_text(encoding="utf-8")
    missing = [kw for kw in REQUIRED_KEYWORDS_EN if kw not in en_text]
    assert not missing, f"Missing required keywords in README.md: {missing}"


def test_required_keywords_zh() -> None:
    """Chinese README must contain all required keywords (drift detection)."""
    zh_text = README_ZH.read_text(encoding="utf-8")
    missing = [kw for kw in REQUIRED_KEYWORDS_ZH if kw not in zh_text]
    assert not missing, f"Missing required keywords in README.zh-CN.md: {missing}"


def test_bilingual_cross_link() -> None:
    """Bilingual READMEs must cross-link each other."""
    en_text = README_EN.read_text(encoding="utf-8")
    zh_text = README_ZH.read_text(encoding="utf-8")
    assert "README.zh-CN.md" in en_text, (
        "README.md does not link to the Chinese translation. "
        "Add a cross-link so bilingual readers can switch."
    )
    assert "README.md" in zh_text, (
        "README.zh-CN.md does not link to the English source. "
        "Add a cross-link so bilingual readers can switch."
    )


def test_bp_i18n_drift_error_code_exists() -> None:
    """BP_I18N_DRIFT error code must be registered in ErrorCode enum.

    Ref: spec §6.2 (错误码). Downstream MCP/agent consumers depend on
    this stable identifier for programmatic error handling.
    """
    assert hasattr(ErrorCode, "BP_I18N_DRIFT"), (
        "ErrorCode.BP_I18N_DRIFT is missing. "
        "Add it in src/builderpulse/core/error_codes.py."
    )
    assert ErrorCode.BP_I18N_DRIFT.value == "BP_I18N_DRIFT", (
        f"ErrorCode.BP_I18N_DRIFT value drifted: "
        f"expected 'BP_I18N_DRIFT', got {ErrorCode.BP_I18N_DRIFT.value!r}"
    )
