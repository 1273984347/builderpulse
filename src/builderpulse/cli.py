"""BuilderPulse CLI — main entry point."""

from __future__ import annotations
import sys
import os
import click
from pathlib import Path

# Ensure MCP mode is not set for CLI
os.environ.pop("BUILDERPULSE_MODE", None)


@click.group()
@click.version_option(version="1.0.0", prog_name="builderpulse")
def cli():
    """BuilderPulse — Track what AI builders are saying."""
    pass


# ── Transcribe ──────────────────────────────────────────────────


@cli.command()
@click.argument("url")
# P2 fix (H3): default=None; resolve from ConfigManager.get() at runtime
# so a user who sets BUILDERPULSE_ENGINE in config.json does not have to
# pass --engine on every CLI invocation.
@click.option(
    "--engine",
    default=None,
    help="Transcription engine (auto/whisper/whisperx/faster-whisper). Defaults to config value.",
)
@click.option(
    "--language",
    default=None,
    help="Language code (zh/en/auto). Defaults to config value.",
)
@click.option(
    "--output",
    default="file",
    type=click.Choice(["file", "stdout"]),
    help="Output destination",
)
def transcribe(url, engine, language, output):
    """Transcribe a video/audio URL to text."""
    from builderpulse.infra.security import is_safe_url

    if not is_safe_url(url):
        click.echo(f"Error: URL not allowed: {url}", err=True)
        sys.exit(1)

    from builderpulse.core.config_manager import ConfigManager
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import Pipeline, step_download, step_transcribe

    cfg = ConfigManager.get()
    if engine is None:
        engine = cfg.engine
    if language is None:
        language = cfg.language

    source = SourceRef.from_url(url)
    click.echo(f"Transcribing: {source.url} ({source.source_type})")

    p = Pipeline(config=cfg)
    p.add(step_download)
    p.add(step_transcribe)
    ctx = p.run(source)

    if ctx.error:
        click.echo(f"Error: {ctx.error}", err=True)
        sys.exit(1)

    if ctx.transcript:
        if output == "stdout":
            click.echo(ctx.transcript.text)
        else:
            out_path = Path(f"{source.native_id}.md")
            out_path.write_text(ctx.transcript.text, encoding="utf-8")
            click.echo(f"Saved to: {out_path}")


# ── Batch ───────────────────────────────────────────────────────


@cli.command()
@click.argument("user_url")
@click.option("--limit", default=20, help="Max videos to process")
# P2 fix (H3): default=None; resolve from ConfigManager.get().engine
@click.option(
    "--engine", default=None, help="Transcription engine (defaults to config value)"
)
@click.option("--concurrency", default=5, type=int, help="Max concurrent items")
@click.option("--qps", default=5.0, type=float, help="Rate limit (requests/sec)")
def batch(user_url, limit, engine, concurrency, qps):
    """Batch transcribe a creator's videos."""
    from builderpulse.batch.manager import BatchManager
    from builderpulse.core.config import Config
    from builderpulse.core.config_manager import ConfigManager

    base_cfg = ConfigManager.get()
    if engine is None:
        engine = base_cfg.engine
    cfg = Config(engine=engine, language=base_cfg.language)
    click.echo(f"Batch mode: {user_url} (limit={limit})")

    # For now, process the single URL; multi-URL resolution is source-dependent
    urls = [user_url]

    mgr = BatchManager(
        config=cfg,
        concurrency=concurrency,
        qps=qps,
    )
    try:
        results = mgr.process_batch(urls)
        succeeded = sum(1 for r in results if r.get("status") == "done")
        failed = sum(1 for r in results if r.get("status") == "failed")
        click.echo(f"Results: {succeeded} succeeded, {failed} failed")
        for r in results:
            if r.get("status") == "done":
                click.echo(f"  OK: {r['url']}")
            else:
                click.echo(
                    f"  FAIL: {r['url']} — {r.get('error', r.get('error_code', 'unknown'))}",
                    err=True,
                )
    finally:
        mgr.shutdown()


# ── Digest ──────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--sources", default="all", help="Sources to fetch (comma-separated or 'all')"
)
# P2 fix (H3): default=None; resolve from ConfigManager.get().language
@click.option(
    "--lang",
    default=None,
    help="Output language (en/zh/bilingual). Defaults to config value.",
)
@click.option("--days", default=1, type=int, help="Lookback days")
@click.option("--deliver", default=None, help="Delivery channels (comma-separated)")
@click.option("--skip-failed", is_flag=True, default=True, help="Skip failed sources")
@click.option("--no-state", is_flag=True, help="Ignore dedup state")
def digest(sources, lang, days, deliver, skip_failed, no_state):
    """Generate AI builder digest."""
    from builderpulse.core.config_manager import ConfigManager
    from builderpulse.core.source_aggregator import fetch_all_sources

    # Load config to get source URLs
    cfg = ConfigManager.get_raw()

    # Resolve --lang from config if not provided
    if lang is None:
        from builderpulse.core.config import Config as _Cfg

        try:
            lang = _Cfg.from_file(ConfigManager.get_config_path()).language
        except Exception:
            lang = "en"

    click.echo(f"Fetching content (last {days} days)...")

    # P2 fix (H4): delegate fetching to the shared aggregator so CLI and
    # MCP code paths don't drift. The aggregator returns (items, errors);
    # we surface per-source counts to the user.
    items, errors = fetch_all_sources(
        cfg,
        days=days,
        sources=sources,
        skip_failed=skip_failed,
    )

    for err in errors:
        # err is "source: message"
        source_name = err.split(":", 1)[0]
        msg = err.split(":", 1)[1].strip() if ":" in err else err
        click.echo(f"  {source_name.capitalize()}s: skipped ({msg})", err=True)

    # Note: per-source item counts are not shown here because the
    # aggregator returns a flat list. The "Total" line below summarises.
    click.echo(f"\nTotal: {len(items)} items")

    if not items:
        click.echo("No new content found.")
        return

    # Output
    for item in items[:20]:
        click.echo(f"\n--- {item.title} ---")
        click.echo(f"  {item.url}")
        click.echo(f"  {item.content[:200]}...")

    # Deliver
    if deliver:
        from builderpulse.deliver import get_channel

        content = "\n\n".join(
            f"## {i.title}\n{i.content[:300]}\n{i.url}" for i in items[:20]
        )
        for ch_name in deliver.split(","):
            ch_name = ch_name.strip()
            try:
                ch = get_channel(ch_name)
                ch.send(content, title="BuilderPulse Digest")
                click.echo(f"Delivered to: {ch_name}")
            except Exception as e:
                click.echo(f"Delivery to {ch_name} failed: {e}", err=True)


# ── Fetch ───────────────────────────────────────────────────────


@cli.command()
@click.argument(
    "source", type=click.Choice(["twitter", "podcast", "blog", "bilibili", "youtube"])
)
@click.option("--limit", default=10, help="Max items")
@click.option("--days", default=7, type=int, help="Lookback days")
@click.option("--user", default=None, help="User ID (for bilibili)")
def fetch(source, limit, days, user):
    """Fetch raw content from a source."""
    from builderpulse.core.config_manager import ConfigManager

    # Load config
    cfg = ConfigManager.get_raw()

    click.echo(f"Fetching from {source}...")

    src = None
    try:
        if source == "podcast":
            from builderpulse.sources.podcast import PodcastSource

            feeds = cfg.get("sources", {}).get("podcast", {}).get("feeds", [])
            src = PodcastSource(feeds=feeds)
            items = src.fetch(days=days, limit=limit)
        elif source == "twitter":
            from builderpulse.sources.twitter import TwitterSource

            accounts = cfg.get("sources", {}).get("twitter", {}).get("accounts", [])
            src = TwitterSource(accounts=accounts)
            items = src.fetch(limit=limit)
        elif source == "blog":
            from builderpulse.sources.blog import BlogSource

            urls = cfg.get("sources", {}).get("blog", {}).get("urls", [])
            src = BlogSource(urls=urls)
            items = src.fetch(days=days, limit=limit)
        elif source == "bilibili":
            if not user:
                click.echo("Error: --user <mid> required for bilibili", err=True)
                sys.exit(1)
            from builderpulse.sources.bilibili import BilibiliSource

            src = BilibiliSource(users=[{"mid": int(user), "name": str(user)}])
            items = src.fetch(limit=limit)
        elif source == "youtube":
            from builderpulse.sources.youtube import YouTubeSource

            src = YouTubeSource()
            items = src.fetch(limit=limit)
        else:
            click.echo(f"Unknown source: {source}")
            return
    finally:
        if src is not None:
            src.close()

    click.echo(f"Found {len(items)} items:")
    for item in items:
        click.echo(f"  [{item.source_type}] {item.title} — {item.url}")


# ── Process ─────────────────────────────────────────────────────


@cli.command()
@click.argument("url")
@click.option("--summarize", is_flag=True, help="Add LLM summary")
@click.option("--deliver", default=None, help="Delivery channels")
def process(url, summarize, deliver):
    """End-to-end pipeline: download → transcribe → summarize → deliver."""
    from builderpulse.infra.security import is_safe_url

    if not is_safe_url(url):
        click.echo(f"Error: URL not allowed: {url}", err=True)
        sys.exit(1)

    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import (
        Pipeline,
        step_download,
        step_transcribe,
        step_summarize,
        step_deliver,
    )

    source = SourceRef.from_url(url)
    click.echo(f"Processing: {source.url}")

    p = Pipeline()
    p.add(step_download)
    p.add(step_transcribe)
    if summarize:
        p.add(step_summarize)
    if deliver:
        for ch in deliver.split(","):
            p.add(step_deliver(ch.strip()))

    ctx = p.run(source)

    if ctx.error:
        click.echo(f"Error: {ctx.error}", err=True)
        sys.exit(1)

    if ctx.transcript:
        click.echo(f"Transcript: {ctx.transcript.word_count} words")
    if ctx.summary:
        click.echo(f"Summary: {ctx.summary[:200]}...")


# ── Clean ───────────────────────────────────────────────────────


@cli.command()
@click.option("--all", "clean_all", is_flag=True, help="Delete all output")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def clean(clean_all, dry_run):
    """Clean old output files and state."""
    from builderpulse.core.state import State

    state = State()
    removed = state.cleanup(max_age_days=7)

    if dry_run:
        click.echo(f"Would remove {removed} state entries")
    else:
        click.echo(f"Removed {removed} state entries")


# ── Config ──────────────────────────────────────────────────────


@cli.group()
def config():
    """Manage BuilderPulse configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    from builderpulse.core.config import Config
    import json

    cfg = Config()
    click.echo(json.dumps(cfg.to_dict(mask_secrets=True), indent=2))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a configuration value and persist to config.json."""
    import json
    import os
    from pathlib import Path

    config_path = Path.home() / ".builderpulse" / "config.json"
    if not config_path.exists():
        click.echo("No config file found. Run 'bp config init' first.", err=True)
        return

    # P1 fix: validate key has no empty segments
    keys = key.split(".")
    if any(not k.strip() for k in keys):
        click.echo(f"Invalid key '{key}': empty segments not allowed", err=True)
        return

    cfg = json.loads(config_path.read_text(encoding="utf-8"))

    # Support nested keys: "delivery.telegram.botToken"
    target = cfg
    for k in keys[:-1]:
        if k not in target or not isinstance(target[k], dict):
            target[k] = {}
        target = target[k]

    # Auto-detect type
    try:
        value = int(value)
    except ValueError:
        try:
            value = float(value)
        except ValueError:
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            # else keep as string

    target[keys[-1]] = value

    # P1 fix: atomic write (write to tmp then replace)
    tmp_path = config_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp_path), str(config_path))

    click.echo(f"Set {key} = {value}")


@config.command("reload")
def config_reload():
    """Reload configuration from disk and notify subscribers."""
    from builderpulse.core.config_manager import ConfigManager

    path = ConfigManager.get_config_path()
    if not Path(path).exists():
        click.echo(f"Config file not found: {path}", err=True)
        sys.exit(1)
    cfg = ConfigManager.reload()
    failed = ConfigManager.get_failed_callbacks()
    click.echo(f"Reloaded config from: {path}")
    click.echo(f"  language={cfg.language}, engine={cfg.engine}, model={cfg.model}")
    if failed:
        click.echo(f"  Warning: {len(failed)} subscriber callback(s) failed", err=True)
        for f_cb in failed:
            click.echo(f"    - {f_cb['callback']}: {f_cb['error']}", err=True)


@config.command("init")
def config_init():
    """Interactive setup — configure BuilderPulse in 60 seconds."""
    from pathlib import Path
    import json

    config_dir = Path.home() / ".builderpulse"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    click.echo()
    click.echo("=== BuilderPulse Setup ===")
    click.echo()

    # Language
    lang = click.prompt(
        "Language", type=click.Choice(["en", "zh", "bilingual"]), default="zh"
    )

    # Transcription engine
    click.echo()
    click.echo("Transcription engine:")
    click.echo("  1. faster-whisper  (recommended, CPU, no PyTorch)")
    click.echo("  2. whisper         (OpenAI Whisper, needs PyTorch)")
    click.echo("  3. whisperx        (best quality, needs GPU)")
    engine_choice = click.prompt(
        "Choose engine", type=click.Choice(["1", "2", "3"]), default="1"
    )
    engine_map = {"1": "faster-whisper", "2": "whisper", "3": "whisperx"}
    engine = engine_map[engine_choice]

    # Content sources
    click.echo()
    click.echo("Enable content sources? (y/n for each)")
    enable_podcast = click.prompt("  Podcast RSS?", type=bool, default=True)
    enable_blog = click.prompt("  Blog scraping?", type=bool, default=True)
    enable_twitter = click.prompt(
        "  X/Twitter? (requires $100/mo API key)", type=bool, default=False
    )
    enable_bilibili = click.prompt("  Bilibili?", type=bool, default=True)

    # Delivery
    click.echo()
    click.echo("Delivery channel (where to send digests):")
    click.echo("  1. stdout  (print to terminal)")
    click.echo("  2. telegram")
    click.echo("  3. lark (飞书)")
    click.echo("  4. dingtalk (钉钉)")
    click.echo("  5. discord")
    click.echo("  6. email (SMTP)")
    delivery_choice = click.prompt(
        "Choose", type=click.Choice(["1", "2", "3", "4", "5", "6"]), default="1"
    )
    delivery_map = {
        "1": "stdout",
        "2": "telegram",
        "3": "lark",
        "4": "dingtalk",
        "5": "discord",
        "6": "email",
    }
    delivery = delivery_map[delivery_choice]

    # Build config
    cfg = {
        "language": lang,
        "engine": engine,
        "model": "base",
        "device": "auto",
        "sources": {
            "twitter": {"enabled": enable_twitter, "accounts": []},
            "podcast": {"enabled": enable_podcast, "feeds": []},
            "blog": {"enabled": enable_blog, "urls": []},
            "bilibili": {"enabled": enable_bilibili, "users": []},
        },
        "delivery": {
            "method": delivery,
            "telegram": {"botToken": "", "chatId": ""},
            "email": {
                "provider": "smtp",
                "smtp": {"host": "", "port": 587, "user": "", "password": ""},
                "to": "",
            },
            "lark": {"webhook_url": "", "secret": ""},
            "dingtalk": {"webhook_url": "", "secret": ""},
            "discord": {"webhook_url": ""},
            "wecom": {"webhook_url": ""},
            "wechat": {"type": "pushplus", "token": ""},
        },
        "remix": {"model": "claude-sonnet-4-6"},
        "workspace": str(config_dir / "output"),
        "cleanup": {"autoTTL": "7d", "maxSize": "5GB"},
    }

    config_file.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    click.echo()
    click.echo(f"Config saved to: {config_file}")
    click.echo()
    click.echo("Next steps:")
    if delivery == "telegram":
        click.echo(
            "  1. Set Telegram bot: bp config set delivery.telegram.botToken <token>"
        )
        click.echo(
            "  2. Set chat ID:     bp config set delivery.telegram.chatId <chat_id>"
        )
    click.echo(f"  Run: bp digest --lang {lang} --deliver {delivery}")
    click.echo()
    click.echo("For MCP integration (Claude Code / Cursor), add to settings:")
    click.echo(
        '  {"mcpServers": {"builderpulse": {"command": "bp", "args": ["serve"]}}}'
    )
    click.echo()


# ── Serve (MCP) ─────────────────────────────────────────────────


@cli.command()
@click.option("--port", default=None, type=int, help="SSE port (default: stdio mode)")
def serve(port):
    """Start MCP server for AI agent integration."""
    os.environ["BUILDERPULSE_MODE"] = "mcp"
    click.echo("Starting BuilderPulse MCP server (stdio)...", err=True)
    from builderpulse.mcp_server import run_mcp_server

    run_mcp_server()


def main():
    cli()


if __name__ == "__main__":
    main()
