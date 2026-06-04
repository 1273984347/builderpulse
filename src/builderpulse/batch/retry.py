"""
Retry with exponential backoff — sync and async versions.

Transient failures (ConnectionError, TimeoutError) are retried with
exponential backoff.  Permanent failures (ValueError, FileNotFoundError, …)
raise immediately so callers can fail fast.

``RetryExhausted.history`` records every attempt so ``BatchManager._classify_error()``
can inspect the root cause chain.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, List, Optional, Tuple, Type

# ── Constants ────────────────────────────────────────────────────────────

RETRYABLE: Tuple[Type[BaseException], ...] = (ConnectionError, TimeoutError)
NON_RETRYABLE: Tuple[Type[BaseException], ...] = (
    ValueError,
    TypeError,
    FileNotFoundError,
    PermissionError,
)

_BACKOFF_CAP = 60.0  # seconds


# ── Exception ────────────────────────────────────────────────────────────


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted.

    Attributes:
        history: List of ``(attempt, exception, delay)`` tuples recorded
            for each failed attempt.
    """

    def __init__(
        self,
        message: str = "Retry exhausted",
        history: Optional[List[Tuple[int, Exception, float]]] = None,
    ) -> None:
        super().__init__(message)
        self.history: List[Tuple[int, Exception, float]] = history or []


# ── Sync retry ───────────────────────────────────────────────────────────


def retry(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    retryable: Tuple[Type[BaseException], ...] = RETRYABLE,
    span: Any = None,
    **kwargs: Any,
) -> Any:
    """Call *fn* with retry and exponential backoff.

    Args:
        fn: Callable to invoke.
        *args: Positional args forwarded to *fn*.
        max_retries: Maximum number of retry attempts (total calls = 1 + max_retries).
        backoff_base: Base for exponential backoff (delay = backoff_base ** attempt).
        retryable: Exception types that trigger a retry.
        span: Optional OTel span; ``span.add_event("retry", {...})`` is called on retry.
        **kwargs: Keyword args forwarded to *fn*.

    Returns:
        The return value of *fn* on success.

    Raises:
        RetryExhausted: When all attempts fail, with full ``history`` attached.
        Exception: Non-retryable exceptions raise immediately (wrapped in RetryExhausted).
    """
    history: List[Tuple[int, Exception, float]] = []

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            delay = 0.0 if attempt == 0 else min(backoff_base ** attempt, _BACKOFF_CAP)
            history.append((attempt, exc, delay))

            # Non-retryable: fail immediately
            if not isinstance(exc, retryable):
                raise RetryExhausted(
                    message=str(exc),
                    history=history,
                ) from exc

            # Last attempt: raise RetryExhausted
            if attempt >= max_retries:
                raise RetryExhausted(
                    message=f"Retry exhausted after {max_retries + 1} attempts",
                    history=history,
                ) from exc

            # OTel integration
            if span is not None:
                try:
                    span.add_event("retry", {"attempt": attempt})
                except Exception:
                    pass

            time.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise RetryExhausted(
        message="Retry exhausted",
        history=history,
    )


# ── Async retry ──────────────────────────────────────────────────────────


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    retryable: Tuple[Type[BaseException], ...] = RETRYABLE,
    span: Any = None,
    **kwargs: Any,
) -> Any:
    """Async version of :func:`retry` using ``await asyncio.sleep``.

    Args and behaviour are identical to :func:`retry`.
    """
    history: List[Tuple[int, Exception, float]] = []

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            delay = 0.0 if attempt == 0 else min(backoff_base ** attempt, _BACKOFF_CAP)
            history.append((attempt, exc, delay))

            # Non-retryable: fail immediately
            if not isinstance(exc, retryable):
                raise RetryExhausted(
                    message=str(exc),
                    history=history,
                ) from exc

            # Last attempt: raise RetryExhausted
            if attempt >= max_retries:
                raise RetryExhausted(
                    message=f"Retry exhausted after {max_retries + 1} attempts",
                    history=history,
                ) from exc

            # OTel integration
            if span is not None:
                try:
                    span.add_event("retry", {"attempt": attempt})
                except Exception:
                    pass

            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise RetryExhausted(
        message="Retry exhausted",
        history=history,
    )
