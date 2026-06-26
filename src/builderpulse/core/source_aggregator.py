"""Source aggregator — single entry point for fetching content from all sources.

Eliminates duplication between the CLI ``digest`` command and the MCP
``bp_digest`` handler. Both call :func:`fetch_all_sources` and render the
``(items, errors)`` tuple according to their own output format.

The aggregator only deals with *fetch* — it does not deliver, summarise,
or render. Callers own those concerns.

Session 31 M2 派生 from LightRAG `kg/__init__.py` STORAGE_IMPLEMENTATIONS + BuilderPulse
`deliver/__init__.py` _CHANNELS 范式 — 把 5 个硬编码 `if _want(...)` 块替换成
`_FETCHERS` 注册表, 加新 source 不用改 `fetch_all_sources`, 跟 deliver/ 12 channel
registry 模式完全对齐.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, List, Optional, Tuple

logger = logging.getLogger("builderpulse.core.source_aggregator")

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

    Session 31 M2: 走 _FETCHERS 注册表 (跟 deliver/_CHANNELS 模式同), 不再硬编码
    5 个 if _want() 块. 加新 source 只需注册到 _FETCHERS.
    """
    source_names = _normalise_sources(sources)

    def _want(name: str) -> bool:
        return source_names is None or name in source_names

    items: List[Any] = []
    errors: List[str] = []

    sources_cfg = config.get("sources", {}) if isinstance(config, dict) else {}

    # Session 31: 走注册表循环 (跟 deliver/__init__.py _CHANNELS 同源)
    for name, fetcher in _FETCHERS.items():
        if not _want(name):
            continue
        items, errors = _safe_fetch(
            items,
            errors,
            name,
            skip_failed,
            lambda f=fetcher, c=sources_cfg: f(c, days=days),
        )

    return items, errors


# ── Source registry (跟 deliver/_CHANNELS 模式 1:1) ──────────────

def _fetch_podcast(sources_cfg: dict, *, days: int) -> List[Any]:
    from builderpulse.sources.podcast import PodcastSource

    feeds = sources_cfg.get("podcast", {}).get("feeds", []) or []
    src = PodcastSource(feeds=feeds)
    try:
        return src.fetch(days=days)
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_twitter(sources_cfg: dict, *, days: int) -> List[Any]:
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


def _fetch_bilibili(sources_cfg: dict, *, days: int) -> List[Any]:
    from builderpulse.sources.bilibili import BilibiliSource

    users = sources_cfg.get("bilibili", {}).get("users", []) or []
    src = BilibiliSource(users=users)
    try:
        return src.fetch()
    finally:
        if hasattr(src, "close"):
            src.close()


def _fetch_youtube(sources_cfg: dict, *, days: int) -> List[Any]:
    from builderpulse.sources.youtube import YouTubeSource

    channels = sources_cfg.get("youtube", {}).get("channels", []) or []
    src = YouTubeSource(channels=channels)
    try:
        return src.fetch()
    finally:
        if hasattr(src, "close"):
            src.close()


# Source fetcher registry — 跟 deliver/_CHANNELS 模式 1:1 (Session 31 M2)
# 加新 source 只需在 _FETCHERS 加一行, 不动 fetch_all_sources
_FETCHERS: dict[str, Callable[..., List[Any]]] = {
    "podcast": _fetch_podcast,
    "twitter": _fetch_twitter,
    "blog": _fetch_blog,
    "bilibili": _fetch_bilibili,
    "youtube": _fetch_youtube,
}


def register_source(name: str, fetcher: Callable[..., List[Any]]) -> None:
    """注册新 source fetcher — 跟 deliver.register_channel 同源.

    Usage (e.g. plugin):
        from builderpulse.core.source_aggregator import register_source
        register_source("rss", _fetch_rss)

    ⚠️ IMPORTANT (Session 31 R1b A-1 caveat):
        Built-in source names cannot be overridden (raises ValueError).
        Custom sources registered here are added to ``_FETCHERS`` BUT NOT to
        ``_VALID_SOURCES`` (immutable tuple — by design, plugin authors must
        NOT mutate module-level state without explicit user approval).

        Workaround for plugin authors who need ``fetch_all_sources(sources=<custom>)``:
        1. Call ``register_source(name, fetcher)`` (registers the fetcher)
        2. Document user to manually edit ``_VALID_SOURCES`` in source_aggregator.py
           (temporary workaround, see v2.3.0 entry_points plugin redesign)

        Or wait for v2.3.0: plugin entry_points auto-discovery + auto-sync.

    Raises:
        ValueError: If name conflicts with built-in source name.
    """
    if name in _VALID_SOURCES:
        raise ValueError(
            f"Cannot register '{name}': conflicts with built-in source name. "
            f"Built-in sources are: {list(_VALID_SOURCES)}. "
            f"Choose a different name (e.g. 'my_custom_{name}')."
        )
    _FETCHERS[name] = fetcher
    # R1b A-1 P3 fix: warning log 提醒 plugin author 需要手动同步 _VALID_SOURCES
    logger.warning(
        "register_source: '%s' added to _FETCHERS. Note: _VALID_SOURCES is "
        "immutable; if you need `fetch_all_sources(sources='%s')` to work, "
        "manually add the name to _VALID_SOURCES in source_aggregator.py "
        "OR use plugin entry_points (v2.3.0 redesign).",
        name,
        name,
    )


def list_sources() -> List[str]:
    return list(_FETCHERS.keys())


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
