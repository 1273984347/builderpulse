"""BatchManager — orchestrates batch download → transcribe → summarize.

Composes :class:`BatchCache`, :class:`DiskGuard`, :class:`RateLimiter`,
and an ``asyncio.Semaphore`` for concurrency control.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from builderpulse.batch.cache import BatchCache
from builderpulse.batch.disk_guard import DiskFullError, DiskGuard
from builderpulse.batch.rate_limiter import RateLimiter
from builderpulse.batch.retry import RetryExhausted
from builderpulse.core.config import Config
from builderpulse.core.config_manager import ConfigManager
from builderpulse.core.error_codes import ErrorCode
from builderpulse.core.models import SourceRef

logger = logging.getLogger("builderpulse.batch")

# ── v2.1.0 spec §3.9: override safety tables ────────────────────────
#
# Experimental sources (anti-scraping risk) require a proxy URL before
# they can be overridden.  Twitch is not experimental but still requires
# OAuth credentials.  Channels each have a single required credential
# field — these mirror what the channel plugins actually consume.

_EXPERIMENTAL_SOURCES = frozenset({"xiaohongshu", "wechat_mp"})

_CREDENTIAL_REQUIRED_SOURCES = frozenset({"twitch"})

_CHANNEL_REQUIRED_FIELDS: Dict[str, str] = {
    "slack": "webhook_url",
    "notion": "token",
    "bark": "device_key",
    "webhook": "url",
}


class BatchManager:
    """Orchestrates batch processing of multiple URLs.

    Args:
        config: BuilderPulse Config (or None for defaults).
        db_path: Path to the SQLite cache database.
        concurrency: Max concurrent items.
        qps: Requests per second rate limit.
        min_disk_bytes: Minimum free disk bytes.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        db_path: Path | str = Path("batch_cache.db"),
        concurrency: int = 5,
        qps: float = 5.0,
        min_disk_bytes: int = 500 * 1024 * 1024,
    ) -> None:
        self._config = config
        self._cache = BatchCache(db_path)
        self._disk = DiskGuard(min_bytes=min_disk_bytes)
        # P1 fix: store params; create asyncio primitives lazily in process_batch_async
        self._concurrency = concurrency
        self._qps = qps

    # ── Public API ────────────────────────────────────────────────────

    def process_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Process a list of URLs synchronously.  Returns list of result dicts.

        Note: This sync path is intentionally sequential with no rate limiting.
        Rate limiting is only needed for async/concurrent paths to avoid
        overwhelming external services. Sequential processing is inherently
        self-throttling.
        """
        results: List[Dict[str, Any]] = []
        for url in urls:
            try:
                result = self._process_item(url)
                results.append(result)
            except Exception as exc:
                error_code = self._classify_error(exc)
                results.append(
                    {
                        "url": url,
                        "status": "failed",
                        "error_code": error_code,
                        "error": str(exc),
                    }
                )
        return results

    async def process_batch_async(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Process URLs concurrently with semaphore + rate limiter."""
        # P1 fix: create asyncio primitives lazily (no event loop in __init__)
        sem = asyncio.Semaphore(self._concurrency)
        limiter = RateLimiter(qps=self._qps)

        async def _guarded(url: str) -> Dict[str, Any]:
            async with sem:
                await limiter.acquire()
                # P2 fix: prefer get_running_loop() — get_event_loop() is
                # deprecated for use inside coroutines (DeprecationWarning
                # since Python 3.10). Fall back only if somehow no loop is
                # running, which would itself be a programming error here.
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    import warnings

                    warnings.warn(
                        "No running event loop; falling back to "
                        "asyncio.get_event_loop() (deprecated)",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._process_item, url)

        tasks = [_guarded(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: List[Dict[str, Any]] = []
        for url, res in zip(urls, results):
            if isinstance(res, Exception):
                error_code = self._classify_error(res)
                out.append(
                    {
                        "url": url,
                        "status": "failed",
                        "error_code": error_code,
                        "error": str(res),
                    }
                )
            else:
                out.append(res)
        return out

    # ── v2.1.0 spec §3.9: run() with override support ──────────────

    def run(
        self,
        *,
        sources_override: Optional[List[str]] = None,
        channels_override: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run a batch with optional source / channel override (spec §3.9).

        If ``sources_override`` is provided, the config's ``enabled_sources``
        is bypassed and the override list is used.  Similarly for
        ``channels_override``.  Safety checks are performed BEFORE any fetch:

        * Experimental sources (``xiaohongshu``, ``wechat_mp``) require
          ``proxy_url`` in the per-source config block.
        * ``twitch`` requires both ``client_id`` and ``client_secret``.
        * Channels validate their required credential field
          (e.g. ``slack`` → ``webhook_url``).

        Missing-credential overrides are logged at ERROR and skipped — the
        method never raises.  Successful overrides of normally-disabled
        integrations are logged at INFO so operators can see opt-ins.

        Returns a ``RunResult``-shaped dict with ``sources`` and
        ``channels`` lists of names that passed validation (i.e. that the
        batch would attempt to fetch / deliver to).  Actual fetch + deliver
        is wired in once the per-source / per-channel plugins land in
        Batch 1 / Batch 2.
        """
        cfg = ConfigManager.get()

        effective_sources, source_errors = self._resolve_sources(cfg, sources_override)
        effective_channels, channel_errors = self._resolve_channels(
            cfg, channels_override
        )

        # Surface the unresolved errors as ERROR logs (safety contract).
        for err in source_errors + channel_errors:
            logger.error(err)

        result: Dict[str, Any] = {
            "sources": effective_sources,
            "channels": effective_channels,
            "skipped": [
                err.split(" ", 1)[0].rstrip(":")
                for err in source_errors + channel_errors
            ],
        }
        logger.info(
            "BatchManager.run: sources=%s channels=%s",
            effective_sources,
            effective_channels,
        )
        return result

    # ── v2.1.0 spec §3.9: override safety helpers ─────────────────

    @staticmethod
    def _resolve_sources(
        cfg: Any, sources_override: Optional[List[str]]
    ) -> tuple[List[str], List[str]]:
        """Return ``(effective_sources, error_messages)``.

        When ``sources_override`` is ``None`` the config's ``enabled_sources``
        is used (or ``[]`` when the field is absent — v2.0.0 compat).
        When an override is given, each name is validated for required
        credentials; failures are reported via the error list and the
        source is removed from ``effective_sources``.
        """
        sources_cfg = getattr(cfg, "sources_config", {}) or {}
        if sources_override is None:
            enabled = getattr(cfg, "enabled_sources", None)
            if not enabled:
                return [], []
            return list(enabled), []

        effective: List[str] = []
        errors: List[str] = []
        for src in sources_override:
            src_cfg = sources_cfg.get(src, {}) if isinstance(sources_cfg, dict) else {}

            if src in _EXPERIMENTAL_SOURCES:
                if not src_cfg.get("proxy_url"):
                    msg = (
                        f"Experimental source {src} requires proxy_url. "
                        "Refusing override."
                    )
                    errors.append(msg)
                    continue

            if src in _CREDENTIAL_REQUIRED_SOURCES:
                if not src_cfg.get("client_id") or not src_cfg.get("client_secret"):
                    msg = (
                        f"Source {src} requires client_id and client_secret. "
                        "Refusing override."
                    )
                    errors.append(msg)
                    continue

            effective.append(src)
            logger.info(
                "Override accepted for source %s (normally disabled or "
                "explicitly requested via CLI/MCP)",
                src,
            )
        return effective, errors

    @staticmethod
    def _resolve_channels(
        cfg: Any, channels_override: Optional[List[str]]
    ) -> tuple[List[str], List[str]]:
        """Return ``(effective_channels, error_messages)``.

        Mirrors :meth:`_resolve_sources` for delivery channels.  Each
        channel name in the override is checked against
        :data:`_CHANNEL_REQUIRED_FIELDS`; missing required fields produce
        an ERROR log and the channel is dropped from the effective list.
        """
        channels_cfg = getattr(cfg, "channels_config", {}) or {}
        if channels_override is None:
            enabled = getattr(cfg, "enabled_channels", None)
            if not enabled:
                return [], []
            return list(enabled), []

        effective: List[str] = []
        errors: List[str] = []
        for ch in channels_override:
            ch_cfg = channels_cfg.get(ch, {}) if isinstance(channels_cfg, dict) else {}
            required = _CHANNEL_REQUIRED_FIELDS.get(ch)
            if required and not ch_cfg.get(required):
                msg = f"Channel {ch} requires {required}. Refusing override."
                errors.append(msg)
                continue
            effective.append(ch)
            logger.info(
                "Override accepted for channel %s (normally disabled or "
                "explicitly requested via CLI/MCP)",
                ch,
            )
        return effective, errors

    # ── Internal ──────────────────────────────────────────────────────

    def _process_item(self, url: str) -> Dict[str, Any]:
        """Single-item pipeline: cache → disk → download → transcribe → summarize → cache."""
        # 1. Cache hit?
        cached = self._cache.get(url)
        if cached and cached.get("status") == "done":
            return cached

        # 2. Disk space check
        workspace = (
            self._config.workspace
            if self._config
            else str(Path.home() / ".builderpulse" / "output")
        )
        self._disk.check(workspace)

        # 3. Download → transcribe → summarize via pipeline
        source = SourceRef.from_url(url)

        from builderpulse.core.pipeline import (
            Pipeline,
            step_download,
            step_transcribe,
            step_summarize,
        )

        p = Pipeline(config=self._config)
        p.add(step_download)
        p.add(step_transcribe)
        p.add(step_summarize)
        ctx = p.run(source)

        if ctx.error:
            self._cache.set(url, "failed", error_code=ErrorCode.BATCH_ITEM_FAILED)
            return {"url": url, "status": "failed", "error": ctx.error}

        result: Dict[str, Any] = {
            "url": url,
            "status": "done",
            "title": source.native_id,
        }
        if ctx.transcript:
            result["word_count"] = ctx.transcript.word_count
        if ctx.summary:
            result["summary"] = ctx.summary[:500]

        self._cache.set(url, "done", result=result)
        return result

    # ── Error classification ──────────────────────────────────────────

    @staticmethod
    def _classify_error(exc: BaseException) -> str:
        """Map exception types to ErrorCode values.

        Walks ``__cause__`` chain to find the root cause.
        """
        # Walk cause chain
        chain: list[BaseException] = []
        current: BaseException | None = exc
        while current is not None:
            chain.append(current)
            current = current.__cause__

        for e in chain:
            if isinstance(e, DiskFullError):
                return ErrorCode.BATCH_DISK_FULL
            if isinstance(e, PermissionError):
                return ErrorCode.DOWNLOAD_FORBIDDEN

        # RetryExhausted: inspect history for root cause type
        if isinstance(exc, RetryExhausted):
            for _, inner, _ in exc.history:
                if isinstance(inner, ConnectionError):
                    return ErrorCode.BATCH_ITEM_FAILED
                if isinstance(inner, TimeoutError):
                    return ErrorCode.BATCH_ITEM_FAILED

        return ErrorCode.BATCH_ITEM_FAILED

    # ── Lifecycle ─────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Close cache and release resources."""
        self._cache.close()
