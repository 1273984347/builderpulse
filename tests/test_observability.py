"""Tests for builderpulse.infra.observability."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import builderpulse.infra.observability as obs


def test_init_telemetry_returns_tracer_and_meter():
    """init_telemetry() returns (tracer, meter) tuple."""
    result = obs.init_telemetry(service_name="builderpulse-test")
    assert isinstance(result, tuple)
    assert len(result) == 2
    tracer, meter = result
    assert tracer is not None
    assert meter is not None


def test_otel_context_attach_detach():
    """otel_context attaches and detaches the context token when OTel is present."""
    mock_context = MagicMock()
    mock_token = MagicMock()
    mock_context.set_value.return_value = "ctx"
    mock_context.attach.return_value = mock_token

    # Temporarily pretend OTel is installed and inject our mock context module
    with patch.object(obs, "_HAS_OTEL", True), \
         patch.object(obs, "_otel_context", mock_context):

        async def _test():
            async with obs.otel_context("my.key", "my.value"):
                mock_context.set_value.assert_called_once_with("my.key", "my.value")
                mock_context.attach.assert_called_once_with("ctx")
            mock_context.detach.assert_called_once_with(mock_token)

        asyncio.run(_test())


def test_no_op_when_not_installed():
    """When opentelemetry is not installed, stubs are returned."""
    original = obs._HAS_OTEL
    obs._HAS_OTEL = False
    try:
        tracer, meter = obs.init_telemetry()
        assert tracer is not None
        assert meter is not None

        async def _test():
            async with obs.otel_context("k", "v"):
                pass  # should not raise

        asyncio.run(_test())
    finally:
        obs._HAS_OTEL = original


def test_init_telemetry_default_service_name():
    """init_telemetry defaults to 'builderpulse'."""
    tracer, meter = obs.init_telemetry()
    assert tracer is not None
    assert meter is not None


def test_noop_tracer_returns_noop_span():
    """NoOpTracer.start_span returns a NoOpSpan with working methods."""
    tracer = obs._NoOpTracer()
    span = tracer.start_span("test-span")
    assert isinstance(span, obs._NoOpSpan)
    # Methods should not raise
    span.set_attribute("key", "value")
    span.end()
    with span:
        pass  # context manager works

def test_noop_meter_instruments():
    """NoOpMeter counter/histogram add/record do not raise."""
    meter = obs._NoOpMeter()
    counter = meter.create_counter("requests")
    histogram = meter.create_histogram("latency")
    counter.add(1)
    histogram.record(0.5)
