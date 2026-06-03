"""Composable content processing pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from builderpulse.core.config import Config
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
    """Summarize content using LLM."""
    if not ctx.transcript and not ctx.error:
        ctx.error = "No transcript to summarize"
        return ctx

    # Placeholder -- actual LLM integration in remix/summarizer.py
    text = ctx.transcript.text if ctx.transcript else ""
    ctx.summary = text[:500] + "..." if len(text) > 500 else text
    return ctx


def step_translate(ctx: PipelineContext) -> PipelineContext:
    """Translate content."""
    # Placeholder -- actual translation in remix/translator.py
    ctx.translation = ctx.summary or (ctx.transcript.text if ctx.transcript else "")
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
    """Get available downloaders."""
    from builderpulse.engines.downloaders.bilibili import BilibiliDownloader
    from builderpulse.engines.downloaders.douyin import DouyinDownloader
    from builderpulse.engines.downloaders.yt_dlp import YtDlpDownloader

    return [YtDlpDownloader(), BilibiliDownloader(), DouyinDownloader()]
