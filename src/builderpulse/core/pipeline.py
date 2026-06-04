"""Composable content processing pipeline."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from builderpulse.batch.retry import retry
from builderpulse.core.config import Config
from builderpulse.core.error_codes import ErrorCode
from builderpulse.core.models import DownloadResult, SourceRef, TranscriptResult
from builderpulse.core.state import State

logger = logging.getLogger("builderpulse.pipeline")


@dataclass
class PipelineContext:
    """Mutable context passed through pipeline steps."""

    source: SourceRef
    config: Config | None = None
    state: State | None = None
    download: DownloadResult | None = None
    transcript: TranscriptResult | None = None
    summary: str | None = None
    translation: str | None = None
    delivery_results: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    errors: list = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Pipeline:
    """Composable pipeline that processes content through chainable steps."""

    def __init__(self, config: Config | None = None, state: State | None = None):
        self.config = config
        self.state = state
        self.steps: list[Callable[[PipelineContext], PipelineContext]] = []

    def add(self, step: Callable[[PipelineContext], PipelineContext]) -> Pipeline:
        """Add a step to the pipeline. Returns self for chaining."""
        self.steps.append(step)
        return self

    def run(self, source: SourceRef) -> PipelineContext:
        """Execute all steps in order. Stops on error."""
        ctx = PipelineContext(source=source, config=self.config, state=self.state)

        for i, step in enumerate(self.steps):
            step_name = getattr(step, "__name__", f"step_{i}")
            logger.info("Running step: %s", step_name)

            try:
                ctx = step(ctx)
            except Exception as e:
                ctx.error = f"{step_name} failed: {e}"
                logger.error(ctx.error)
                break

            if ctx.error:
                logger.warning("Step %s set error: %s", step_name, ctx.error)
                break

        return ctx


# -- Predefined steps --------------------------------------------------------


def step_download(ctx: PipelineContext) -> PipelineContext:
    """Download content from source."""
    downloaders = _get_downloaders(ctx.config)
    for dl in downloaders:
        if dl.can_handle(ctx.source):
            output_dir = Path(
                ctx.config.workspace if ctx.config else "~/.builderpulse/output/downloads"
            ).expanduser()
            ctx.download = dl.download(ctx.source, output_dir)
            return ctx

    ctx.error = f"No downloader found for {ctx.source.source_type}"
    return ctx


def step_transcribe(ctx: PipelineContext) -> PipelineContext:
    """Transcribe downloaded audio/video."""
    if not ctx.download:
        ctx.error = "No download result to transcribe"
        return ctx

    try:
        from builderpulse.engines.transcribers import get_transcriber

        engine = ctx.config.engine if ctx.config and ctx.config.engine != "auto" else "auto"
        transcriber = get_transcriber(engine)
        ctx.transcript = transcriber.transcribe(
            Path(ctx.download.path),
            language=ctx.config.language if ctx.config else None,
        )
    except ImportError as e:
        ctx.error = str(e)
    except Exception as e:
        ctx.error = f"Transcription failed: {e}"

    return ctx


def step_summarize(ctx: PipelineContext) -> PipelineContext:
    """Summarize content using LLM with retry and fallback."""
    if not ctx.transcript and not ctx.error:
        ctx.error = "No transcript to summarize"
        return ctx

    text = ctx.transcript.text if ctx.transcript else ""
    fallback = text[:500]

    try:
        from builderpulse.remix.summarizer import Summarizer, get_provider

        provider = get_provider(
            model=ctx.config.model if ctx.config else "auto",
            api_key=ctx.config.api_key if ctx.config else None,
        )
        summarizer = Summarizer(provider)
        ctx.summary = retry(
            summarizer.summarize,
            text,
            max_retries=3,
            backoff_base=2.0,
        )
    except Exception as e:
        logger.warning("Summarize failed, using fallback: %s", e)
        ctx.summary = fallback
        ctx.errors.append({"error_code": ErrorCode.SUMMARIZE_FAILED, "detail": str(e)})

    return ctx


def step_translate(ctx: PipelineContext) -> PipelineContext:
    """Translate content using LLM with retry and fallback."""
    original = ctx.summary or (ctx.transcript.text if ctx.transcript else "")
    target_lang = ctx.config.language if ctx.config else "zh"

    try:
        from builderpulse.remix.summarizer import get_provider
        from builderpulse.remix.translator import Translator

        provider = get_provider(
            model=ctx.config.model if ctx.config else "auto",
            api_key=ctx.config.api_key if ctx.config else None,
        )
        translator = Translator(provider)
        ctx.translation = retry(
            translator.translate,
            original,
            target_lang,
            max_retries=3,
            backoff_base=2.0,
        )
    except Exception as e:
        logger.warning("Translate failed, using fallback: %s", e)
        ctx.translation = original
        ctx.errors.append({"error_code": ErrorCode.TRANSLATE_FAILED, "detail": str(e)})

    return ctx


def step_deliver(channel: str) -> Callable:
    """Create a delivery step for a specific channel."""

    def _deliver(ctx: PipelineContext) -> PipelineContext:
        content = ctx.translation or ctx.summary or (ctx.transcript.text if ctx.transcript else "")
        if not content:
            ctx.error = "No content to deliver"
            return ctx

        try:
            from builderpulse.deliver import get_channel

            ch = get_channel(channel)
            ctx.delivery_results[channel] = ch.send(content)
        except Exception as e:
            ctx.error = f"Delivery to {channel} failed: {e}"
            ctx.delivery_results[channel] = False

        return ctx

    _deliver.__name__ = f"step_deliver_{channel}"
    return _deliver


def _get_downloaders(config: Config | None) -> list:
    """Get available downloaders, preferring plugin registry."""
    from builderpulse.plugins import PluginRegistry

    registry = PluginRegistry()
    downloaders = list(registry.list_plugins("downloaders").values())
    if not downloaders:
        # Fallback to hardcoded defaults
        from builderpulse.engines.downloaders.bilibili import BilibiliDownloader
        from builderpulse.engines.downloaders.douyin import DouyinDownloader
        from builderpulse.engines.downloaders.yt_dlp import YtDlpDownloader

        downloaders = [YtDlpDownloader(), BilibiliDownloader(), DouyinDownloader()]
    return downloaders
