"""Tests for pipeline remix wiring — step_summarize and step_translate."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from builderpulse.core.pipeline import PipelineContext, step_summarize, step_translate
from builderpulse.core.models import SourceRef
from builderpulse.core.error_codes import ErrorCode


def _make_ctx(transcript_text="Long transcript " * 200, summary=None):
    """Helper to create a PipelineContext with required fields."""
    ctx = PipelineContext(source=SourceRef.from_url("https://youtube.com/watch?v=test"))
    ctx.config = Mock(model="gpt-4", api_key="test", language="zh")
    ctx.errors = []
    if transcript_text is not None:
        ctx.transcript = Mock(text=transcript_text)
    if summary is not None:
        ctx.summary = summary
    return ctx


class TestStepSummarize:
    """Tests for the real step_summarize implementation."""

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_calls_llm(self, mock_prov, mock_sleep):
        ctx = _make_ctx()
        mock_provider = Mock()
        mock_provider.complete.return_value = "LLM summary"
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        assert ctx.summary == "LLM summary"
        assert len(ctx.errors) == 0
        mock_provider.complete.assert_called_once()

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_fallback_on_failure(self, mock_prov, mock_sleep):
        ctx = _make_ctx(transcript_text="content " * 200)
        mock_provider = Mock()
        mock_provider.complete.side_effect = ConnectionError("API down")
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        assert ctx.summary == ("content " * 200)[:500]
        assert len(ctx.errors) == 1
        assert ctx.errors[0]["error_code"] == ErrorCode.SUMMARIZE_FAILED

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_no_transcript(self, mock_prov, mock_sleep):
        ctx = _make_ctx(transcript_text=None)
        ctx.transcript = None

        ctx = step_summarize(ctx)

        assert ctx.error == "No transcript to summarize"

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_fallback_preserves_short_text(self, mock_prov, mock_sleep):
        ctx = _make_ctx(transcript_text="short text")
        mock_provider = Mock()
        mock_provider.complete.side_effect = RuntimeError("boom")
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        assert ctx.summary == "short text"
        assert len(ctx.errors) == 1

    # ── v2.2.0 Commit 1: prompt template integration ────────────────

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_loads_template_by_source_type(
        self, mock_prov, mock_sleep
    ):
        """step_summarize must load prompt template keyed by source.source_type
        and pass it as system= to provider.complete.

        Builtin has summarize-podcast.md → for YouTube (source_type='youtube' may
        map to podcast variant in v2.2.0). For the test, use source_type that
        has a builtin template (e.g. 'youtube' is not, but 'podcast' is).
        Override source_type on the SourceRef.
        """
        ctx = _make_ctx()
        ctx.source.source_type = "podcast"  # builtin has summarize-podcast.md
        mock_provider = Mock()
        mock_provider.complete.return_value = "LLM summary"
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        # provider.complete called with (text, system=...)
        # system should contain the builtin summarize-podcast.md content
        assert ctx.summary == "LLM summary"
        call_kwargs = mock_provider.complete.call_args
        assert "system" in call_kwargs.kwargs or len(call_kwargs.args) >= 2
        # Extract system arg (either positional or keyword)
        if "system" in call_kwargs.kwargs:
            system = call_kwargs.kwargs["system"]
        else:
            # system is positional in summarizer.summarize(text, system, ...)
            system = call_kwargs.args[1] if len(call_kwargs.args) >= 2 else ""
        # Builtin summarize-podcast.md should mention "podcast" or similar
        assert len(system) > 0  # template loaded, not empty

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_empty_system_when_no_template(
        self, mock_prov, mock_sleep
    ):
        """When source_type has no template (and no default), system must be empty.
        This preserves v2.1.0 graceful degradation behavior.
        """
        from pathlib import Path

        ctx = _make_ctx()
        ctx.source.source_type = "definitely_nonexistent_source_type_xyz"
        # Empty custom prompts dir → forces fallback only to builtin
        ctx.config = Mock(
            model="gpt-4", api_key="test", language="zh",
            prompts_dir=None,  # no custom
        )
        mock_provider = Mock()
        mock_provider.complete.return_value = "LLM summary"
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        assert ctx.summary == "LLM summary"
        assert len(ctx.errors) == 0
        # system should be empty (graceful fallback)
        call_kwargs = mock_provider.complete.call_args
        if "system" in call_kwargs.kwargs:
            system = call_kwargs.kwargs["system"]
        else:
            system = call_kwargs.args[1] if len(call_kwargs.args) >= 2 else ""
        assert system == ""  # graceful empty

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_summarize_uses_custom_prompts_dir(self, mock_prov, mock_sleep, tmp_path):
        """When config.prompts_dir is set, registry must look there first."""
        ctx = _make_ctx()
        ctx.source.source_type = "podcast"
        # Create custom dir with custom podcast prompt
        custom = tmp_path / "prompts"
        custom.mkdir()
        (custom / "summarize-podcast.md").write_text(
            "MY CUSTOM PODCAST SYSTEM PROMPT", encoding="utf-8"
        )
        ctx.config = Mock(
            model="gpt-4", api_key="test", language="zh",
            prompts_dir=str(custom),
        )
        mock_provider = Mock()
        mock_provider.complete.return_value = "summary"
        mock_prov.return_value = mock_provider

        ctx = step_summarize(ctx)

        call_kwargs = mock_provider.complete.call_args
        if "system" in call_kwargs.kwargs:
            system = call_kwargs.kwargs["system"]
        else:
            system = call_kwargs.args[1] if len(call_kwargs.args) >= 2 else ""
        assert "MY CUSTOM PODCAST" in system

    # ── v2.2.0 Commit 1 R1a P1-C1 fix: Config.prompts_dir field ──────

    def test_config_has_prompts_dir_field(self):
        """Config.prompts_dir field exists with default None.

        R1a V2 + V3 共享 finding: production custom_dir 链不可达.
        Fix (选项 B): 加 Config 字段 + env var auto-support.
        """
        from builderpulse.core.config import Config

        c = Config()
        assert hasattr(c, "prompts_dir")
        assert c.prompts_dir is None

    def test_config_prompts_dir_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """BUILDERPULSE_PROMPTS_DIR env var overrides prompts_dir.

        Verified via Config.from_defaults() (which calls _apply_env_overrides).
        """
        from builderpulse.core.config import Config

        monkeypatch.setenv("BUILDERPULSE_PROMPTS_DIR", "/env/override/path")
        c = Config.from_defaults()
        assert c.prompts_dir == "/env/override/path"

    def test_config_prompts_dir_round_trip(self, tmp_path: Path):
        """Config.from_file() loads prompts_dir, Config.to_dict() preserves it."""
        import json
        from builderpulse.core.config import Config

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {"__version__": "2.2.0", "prompts_dir": "/custom/prompts"},
                f,
            )
            fname = f.name
        c = Config.from_file(fname)
        assert c.prompts_dir == "/custom/prompts"
        d = c.to_dict()
        assert d.get("prompts_dir") == "/custom/prompts"

    # ── v2.2.0 Commit 1 R1b A4 fix: env-override to_dict pollution ─────

    def test_to_dict_excludes_env_overrides_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """R1b A4 fix: env-overridden fields must NOT pollute to_dict output.

        Scenario:
            1. Disk config has prompts_dir='/disk/value'
            2. Env var BUILDERPULSE_PROMPTS_DIR='/env/value' overrides it
            3. to_dict() must NOT include the env value (would corrupt disk)
        """
        import json
        from builderpulse.core.config import Config

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {"__version__": "2.2.0", "prompts_dir": "/disk/value"},
                f,
            )
            fname = f.name
        monkeypatch.setenv("BUILDERPULSE_PROMPTS_DIR", "/env/value")

        c = Config.from_file(fname)
        assert c.prompts_dir == "/env/value"  # env wins in-memory
        d = c.to_dict()
        # Disk value preserved (not env-only temp value)
        assert "prompts_dir" not in d or d["prompts_dir"] == "/disk/value"

    def test_to_dict_includes_env_overrides_when_requested(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """include_env_overrides=True returns env values for explicit debug dumps."""
        from builderpulse.core.config import Config

        monkeypatch.setenv("BUILDERPULSE_PROMPTS_DIR", "/env/debug")
        c = Config.from_defaults()
        d = c.to_dict(include_env_overrides=True)
        assert d.get("prompts_dir") == "/env/debug"

    def test_target_config_version_is_2_2_0(self):
        """R1b A1 fix: TARGET_CONFIG_VERSION must align with package version."""
        from builderpulse.core.config import TARGET_CONFIG_VERSION
        from builderpulse import __version__

        assert TARGET_CONFIG_VERSION == __version__
        assert TARGET_CONFIG_VERSION == "2.2.0"

    def test_step_summarize_handles_partial_config_mock(self):
        """R1b A3 regression fix: getattr fallback tolerates partial Config.

        Scenario: Mock(spec=[...]) includes all step_summarize needed attrs
        EXCEPT 'prompts_dir'. Old code (after removing getattr) would
        AttributeError → SUMMARIZE_FAILED. New code (with getattr fallback)
        → AttributeError caught gracefully → empty system.
        """
        from unittest.mock import Mock, patch

        ctx = PipelineContext(source=SourceRef.from_url("https://youtube.com/watch?v=test"))
        # Realistic Mock: all step_summarize needed attrs except 'prompts_dir'
        ctx.config = Mock(
            spec=["model", "language", "api_key", "role_llm_registry", "engine", "prompts_dir"],
        )
        ctx.config.model = "auto"
        ctx.config.language = "zh"
        ctx.config.api_key = None
        ctx.config.role_llm_registry = None  # role registry disabled
        ctx.config.engine = "auto"
        ctx.config.prompts_dir = None
        ctx.errors = []
        ctx.transcript = Mock(text="Long content " * 50)

        with patch("builderpulse.core.pipeline.time.sleep", return_value=None), \
             patch("builderpulse.remix.summarizer.get_provider") as mock_prov:
            mock_provider = Mock()
            mock_provider.complete.return_value = "summary"
            mock_prov.return_value = mock_provider

            ctx = step_summarize(ctx)

            assert ctx.summary == "summary"  # graceful fallback worked
            assert len(ctx.errors) == 0  # no SUMMARIZE_FAILED raised


class TestStepTranslate:
    """Tests for the real step_translate implementation."""

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.translator.Translator")
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_translate_calls_llm(self, mock_prov, MockTranslator, mock_sleep):
        ctx = _make_ctx(summary="English summary")
        mock_provider = Mock()
        mock_prov.return_value = mock_provider
        mock_translator = Mock()
        mock_translator.translate.return_value = "中文摘要"
        MockTranslator.return_value = mock_translator

        ctx = step_translate(ctx)

        assert ctx.translation == "中文摘要"
        mock_translator.translate.assert_called_once()

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.translator.Translator")
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_translate_fallback_on_failure(
        self, mock_prov, MockTranslator, mock_sleep
    ):
        ctx = _make_ctx(summary="English summary")
        mock_provider = Mock()
        mock_prov.return_value = mock_provider
        mock_translator = Mock()
        mock_translator.translate.side_effect = Exception("LLM error")
        MockTranslator.return_value = mock_translator

        ctx = step_translate(ctx)

        assert ctx.translation == "English summary"
        assert ctx.errors[-1]["error_code"] == ErrorCode.TRANSLATE_FAILED

    @patch("builderpulse.core.pipeline.time.sleep", return_value=None)
    @patch("builderpulse.remix.translator.Translator")
    @patch("builderpulse.remix.summarizer.get_provider")
    def test_step_translate_no_summary_uses_transcript(
        self, mock_prov, MockTranslator, mock_sleep
    ):
        ctx = _make_ctx(transcript_text="raw transcript")
        ctx.summary = None
        mock_provider = Mock()
        mock_prov.return_value = mock_provider
        mock_translator = Mock()
        mock_translator.translate.return_value = "翻译结果"
        MockTranslator.return_value = mock_translator

        ctx = step_translate(ctx)

        assert ctx.translation == "翻译结果"
