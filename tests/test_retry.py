"""Tests for builderpulse.batch.retry."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch

from builderpulse.batch.retry import retry, retry_async, RetryExhausted


def test_retry_success_first_attempt():
    """No retry needed when fn succeeds on first call."""
    fn = Mock(return_value=42)
    assert retry(fn, backoff_base=0.01) == 42
    assert fn.call_count == 1


def test_retry_succeeds_after_failures():
    """Retry succeeds after transient failures."""
    fn = Mock(side_effect=[ConnectionError("f1"), ConnectionError("f2"), 42])
    assert retry(fn, backoff_base=0.01) == 42
    assert fn.call_count == 3


def test_retry_exhausted_has_history():
    """RetryExhausted records attempt history."""
    fn = Mock(side_effect=ConnectionError("fail"))
    with pytest.raises(RetryExhausted) as exc_info:
        retry(fn, max_retries=2, backoff_base=0.01)
    # 1 initial + 2 retries = 3 total attempts
    assert len(exc_info.value.history) == 3
    for attempt, exc, delay in exc_info.value.history:
        assert isinstance(attempt, int)
        assert isinstance(exc, ConnectionError)
        assert isinstance(delay, float)


def test_retry_non_retryable_raises_immediately():
    """Non-retryable exceptions raise immediately (wrapped in RetryExhausted), no retries."""
    fn = Mock(side_effect=ValueError("bad"))
    with pytest.raises(RetryExhausted) as exc_info:
        retry(fn, max_retries=3, backoff_base=0.01)
    assert fn.call_count == 1
    assert len(exc_info.value.history) == 1
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_retry_non_retryable_wraps_in_exhausted():
    """Non-retryable exceptions get wrapped with history."""
    fn = Mock(side_effect=TypeError("bad"))
    with pytest.raises(RetryExhausted) as exc_info:
        retry(fn, max_retries=3, backoff_base=0.01)
    assert len(exc_info.value.history) == 1
    assert isinstance(exc_info.value.history[0][1], TypeError)


@patch("time.sleep")
def test_retry_exponential_backoff(mock_sleep):
    """Delays increase exponentially."""
    fn = Mock(side_effect=ConnectionError("fail"))
    with pytest.raises(RetryExhausted) as exc_info:
        retry(fn, max_retries=3, backoff_base=2.0)
    delays = [d for _, _, d in exc_info.value.history]
    # First attempt has delay 0 (before any sleep)
    assert delays[0] == 0.0
    # Subsequent delays should be 2^attempt, capped at 60
    assert delays[1] == pytest.approx(2.0, abs=0.01)
    assert delays[2] == pytest.approx(4.0, abs=0.01)
    assert delays[3] == pytest.approx(8.0, abs=0.01)
    # Sleep is called for attempts 0..max_retries-1 (not the last attempt)
    # Attempt 0: delay=0 (sleep called with 0.0), Attempt 1: delay=2, Attempt 2: delay=4
    # Attempt 3: last attempt, raises before sleep
    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(0.0)
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)


@patch("time.sleep")
def test_retry_backoff_capped_at_60(mock_sleep):
    """Backoff delay is capped at 60 seconds."""
    fn = Mock(side_effect=ConnectionError("fail"))
    with pytest.raises(RetryExhausted) as exc_info:
        retry(fn, max_retries=2, backoff_base=100.0)
    delays = [d for _, _, d in exc_info.value.history]
    # First attempt delay is 0, second should be capped at 60, third also capped
    assert delays[0] == 0.0
    assert delays[1] == 60.0
    assert delays[2] == 60.0
    # Sleep called for attempt 0 (delay=0) and attempt 1 (delay=60)
    # Attempt 2 is last, raises before sleep
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.0)
    mock_sleep.assert_any_call(60.0)


@patch("time.sleep")
def test_retry_with_span(mock_sleep):
    """span.add_event is called on each retry."""
    span = Mock()
    fn = Mock(side_effect=[ConnectionError("f1"), 42])
    retry(fn, backoff_base=2.0, span=span)
    # Attempt 0 fails, not last attempt -> span.add_event called with attempt=0
    assert span.add_event.call_count == 1
    span.add_event.assert_called_with("retry", {"attempt": 0})


@pytest.mark.asyncio
async def test_retry_async_success():
    """Async retry succeeds on first attempt."""
    fn = Mock(return_value=42)
    assert await retry_async(fn, backoff_base=0.01) == 42


@pytest.mark.asyncio
async def test_retry_async_succeeds_after_failures():
    """Async retry succeeds after transient failures."""
    fn = Mock(side_effect=[ConnectionError("f1"), ConnectionError("f2"), 42])
    assert await retry_async(fn, backoff_base=0.01) == 42
    assert fn.call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausted():
    """Async retry raises RetryExhausted when all attempts fail."""
    fn = Mock(side_effect=ConnectionError("fail"))
    with pytest.raises(RetryExhausted) as exc_info:
        await retry_async(fn, max_retries=2, backoff_base=0.01)
    assert len(exc_info.value.history) == 3


@pytest.mark.asyncio
async def test_retry_async_non_retryable():
    """Async retry raises immediately for non-retryable exceptions (wrapped in RetryExhausted)."""
    fn = Mock(side_effect=ValueError("bad"))
    with pytest.raises(RetryExhausted) as exc_info:
        await retry_async(fn, max_retries=3, backoff_base=0.01)
    assert fn.call_count == 1
    assert len(exc_info.value.history) == 1
    assert isinstance(exc_info.value.__cause__, ValueError)
