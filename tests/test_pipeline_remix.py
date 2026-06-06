"""Tests for pipeline remix wiring — step_summarize and step_translate."""

from unittest.mock import Mock, patch
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
