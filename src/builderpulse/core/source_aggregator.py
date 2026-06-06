"""Source aggregator — single entry point for fetching content from all sources.

Eliminates duplication between the CLI ``digest`` command and the MCP
``bp_digest`` handler. Both call :func:`fetch_all_sources` and render the
``(items, errors)`` tuple according to their own output format.

The aggregator only deals with *fetch* — it does not deliver, summarise,
or render. Callers own those concerns.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Tuple

# Sentinel meaning "fetch every configured source".
ALL_SOURCES = "all"

_VALID_SOURCES = ("podcast", "twitter", "blog", "bilibili", "youtube")


def _normalise_sources(sources: Optional[Iterable[str] | str]) -> Optional[List[str]]:
    """Return the list of source names to fetch, or ``None`` for 'all'.

    Accepts either a comma-separated string (CLI form) or an iterable of
    names (MCP form). Returns ``None`` when the input is empty or equals
    the sentinel :data:`ALL_SOURCES` so callers can fast-path.
    """
    if sources is None:
        return None
    if isinstance(sources, str):
        if sources.strip().lower() == ALL_SOURCES:
            return None
        names = [s.strip() for s in sources.split(",") if s.strip()]
    else:
        names = [str(s).strip() for s in sources if str(s).strip()]

    if not names:
        return None
    # Filter out unknown names — they're treated as if not requested.
    return [n for n in names if n in _VALID_SOURCES]


def fetch_all_sources(
    config: dict,
    *,
    days: int = 1,
    sources: Optional[Iterable[str] | str] = None,
    skip_failed: bool = True,
) -> Tuple[List[Any], List[str]]:
    """Fetch content items from all configured sources.

    Parameters
    ----------
    config
        The raw config dict (as returned by :meth:`ConfigManager.get_raw`).
        Must contain a ``"sources"`` key with sub-dicts per source type.
    days
        Lookback window for sources that support time-based filtering.
    sources
        Optional inclusion filter. ``None`` (or ``"all"``) fetches every
        configured source. Otherwise pass a comma-separated string or an
        iterable of source names.
    skip_failed
        If True (default), exceptions in a single source are collected into
        ``errors`` and the loop continues. If False, the first exception
        propagates.

    Returns
    -------
    (items, errors)
        ``items``  — list of :class:`FeedItem` (or whatever the source's
                     ``fetch()`` returns).
        ``errors`` — list of ``"source_name: message"`` strings. Empty when
                     every source succeeded.
    """
    source_names = _normalise_sources(sources)

    def _want(name: str) -> bool:
        return source_names is None or name in source_names

    items: List[Any] = []
    errors: List[str] = []

    sources_cfg = config.get("sources", {}) if isinstance(config, dict) else {}

    if _want("podcast"):
        items, errors = _safe_fetch(
            items,
            errors,
            "podcast",
            skip_failed,
            lambda: _fetch_podcast(sources_cfg, days=days),
        )

    if _want("twitter"):
        items, errors = _safe_fetch(
            items,
            errors,
            "twitter",
            skip_failed,
            lambda: _fetch_twitter(sources_cfg),
        )

    if _want("blog"):
        items, errors = _safe_fetch(
            items,
            errors,
            "blog",
            skip_failed,
            lambda: _fetch_blog(sources_cfg, days=days),
        )

    if _want("bilibili"):
        items, errors = _safe_fetch(
            items,
            errors,
            "bilibili",
            skip_failed,
            lambda: _fetch_bilibili(sources_cfg),
        )

    if _want("youtube"):
        items, errors = _safe_fetch(
            items,
            errors,
            "youtube",
            skip_failed,
            lambda: _fetch_youtube(sources_cfg),
        )

    return items, errors


# ── Internals ────────────────────────────────────────────────────────────


def _safe_fetch(
    items: List[Any],
    errors: List[str],
    name: str,
    skip_failed: bool,
    fetcher,
) -> Tuple[List[Any], List[str]]:
    """Run *fetcher* with the standard try/except protocol.

    The fetcher is responsible for instantiating the source and calling
    ``.fetch(...)`` *and* closing it. This helper only handles exception
    capture so each source can short-circuit with the same error format.
    """
    try:
        fetched = fetcher()
        if fetched is None:
            return items, errors
        items.extend(fetched)
    except Exception as exc:
        if not skip_failed:
            raise
        errors.append(f"{name}: {exc}")
    return items, errors


def _fetch_podcast(sources_cfg: dict, *, days: int) -> List[Any]:
    from builderpulse.sources.podcast import PodcastSource

    feeds = sources_cfg.get("podcast", {}).get("feeds", []) or []
    src = PodcastSource(feeds=feeds)
    try:
        return src.fetch(days=days)
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_twitter(sources_cfg: dict) -> List[Any]:
    from builderpulse.sources.twitter import TwitterSource

    accounts = sources_cfg.get("twitter", {}).get("accounts", []) or []
    src = TwitterSource(accounts=accounts)
    try:
        return src.fetch()
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_blog(sources_cfg: dict, *, days: int) -> List[Any]:
    from builderpulse.sources.blog import BlogSource

    urls = sources_cfg.get("blog", {}).get("urls", []) or []
    src = BlogSource(urls=urls)
    try:
        return src.fetch(days=days)
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_bilibili(sources_cfg: dict) -> List[Any]:
    from builderpulse.sources.bilibili import BilibiliSource

    users = sources_cfg.get("bilibili", {}).get("users", []) or []
    src = BilibiliSource(users=users)
    try:
        return src.fetch()
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_youtube(sources_cfg: dict) -> List[Any]:
    from builderpulse.sources.youtube import YouTubeSource

    channels = sources_cfg.get("youtube", {}).get("channels", []) or []
    src = YouTubeSource(channels=channels)
    try:
        return src.fetch()
    finally:
        if hasattr(src, "close"):
            src.close()
