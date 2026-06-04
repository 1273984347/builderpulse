"""OpenTelemetry integration — tracer, meter, and context helpers.

Falls back to no-op stubs when opentelemetry-api is not installed.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Tuple

_otel_context = None  # type: ignore[assignment]

try:
    from opentelemetry import context as _otel_context  # noqa: F811
    from opentelemetry import trace, metrics
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


# ---------------------------------------------------------------------------
# No-op stubs used when OTel is not installed
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """Minimal span stub."""
    def set_attribute(self, *a: Any, **kw: Any) -> None: ...
    def end(self) -> None: ...
    def __enter__(self): return self
    def __exit__(self, *a: Any) -> None: ...

class _NoOpTracer:
    """Tracer that returns no-op spans."""
    def start_span(self, name: str, **kw: Any) -> _NoOpSpan:
        return _NoOpSpan()

class _NoOpMeter:
    """Meter that returns no-op instruments."""
    def create_counter(self, name: str, **kw: Any) -> Any:
        return self
    def create_histogram(self, name: str, **kw: Any) -> Any:
        return self
    def add(self, *a: Any, **kw: Any) -> None: ...
    def record(self, *a: Any, **kw: Any) -> None: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_telemetry(
    service_name: str = "builderpulse",
) -> Tuple[Any, Any]:
    """Return ``(tracer, meter)`` from OpenTelemetry.

    When ``opentelemetry-api`` is not installed, returns no-op stubs so
    callers never need to guard imports.
    """
    if _HAS_OTEL:
        tracer = trace.get_tracer(service_name)
        meter = metrics.get_meter(service_name)
        return tracer, meter

    return _NoOpTracer(), _NoOpMeter()


@asynccontextmanager
async def otel_context(key: str, value: str) -> AsyncIterator[None]:
    """Attach an OTel context key/value for the duration of the block.

    Works as a no-op when OTel is not installed.
    """
    if _HAS_OTEL:
        ctx = _otel_context.set_value(key, value)
        token = _otel_context.attach(ctx)
        try:
            yield
        finally:
            _otel_context.detach(token)
    else:
        yield
