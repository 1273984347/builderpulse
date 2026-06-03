"""Tests for the composable pipeline."""

from builderpulse.core.models import SourceRef
from builderpulse.core.pipeline import Pipeline, PipelineContext


def test_pipeline_empty():
    """Empty pipeline returns context without error."""
    p = Pipeline()
    source = SourceRef(source_type="youtube", native_id="abc", url="https://yt.com")
    ctx = p.run(source)
    assert ctx.source == source
    assert ctx.error is None


def test_pipeline_step_modifies_context():
    """Steps can modify the context."""

    def my_step(ctx: PipelineContext) -> PipelineContext:
        ctx.metadata["visited"] = True
        return ctx

    p = Pipeline()
    p.add(my_step)
    source = SourceRef(source_type="test", native_id="1", url="http://t")
    ctx = p.run(source)
    assert ctx.metadata["visited"] is True


def test_pipeline_stops_on_error():
    """Pipeline stops when a step sets error."""

    def fail_step(ctx: PipelineContext) -> PipelineContext:
        ctx.error = "boom"
        return ctx

    def after_step(ctx: PipelineContext) -> PipelineContext:
        ctx.metadata["should_not_run"] = True
        return ctx

    p = Pipeline()
    p.add(fail_step)
    p.add(after_step)
    source = SourceRef(source_type="test", native_id="1", url="http://t")
    ctx = p.run(source)
    assert ctx.error == "boom"
    assert "should_not_run" not in ctx.metadata


def test_pipeline_stops_on_exception():
    """Pipeline catches exceptions and sets error."""

    def explode(ctx: PipelineContext) -> PipelineContext:
        raise ValueError("unexpected")

    p = Pipeline()
    p.add(explode)
    source = SourceRef(source_type="test", native_id="1", url="http://t")
    ctx = p.run(source)
    assert "unexpected" in ctx.error


def test_pipeline_chaining():
    """Pipeline.add returns self for chaining."""
    p = Pipeline()
    result = p.add(lambda ctx: ctx).add(lambda ctx: ctx)
    assert result is p
    assert len(p.steps) == 2


def test_step_summarize_without_transcript():
    """step_summarize sets error when no transcript."""
    from builderpulse.core.pipeline import step_summarize

    ctx = PipelineContext(source=SourceRef(source_type="test", native_id="1", url="http://t"))
    ctx = step_summarize(ctx)
    assert ctx.error is not None
