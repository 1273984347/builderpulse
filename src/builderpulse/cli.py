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
@click.option("--engine", default="auto", help="Transcription engine (auto/whisper/whisperx/faster-whisper)")
@click.option("--language", default=None, help="Language code (zh/en/auto)")
@click.option("--output", default="file", type=click.Choice(["file", "stdout"]), help="Output destination")
def transcribe(url, engine, language, output):
    """Transcribe a video/audio URL to text."""
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import Pipeline, PipelineContext, step_download, step_transcribe

    source = SourceRef.from_url(url)
    click.echo(f"Transcribing: {source.url} ({source.source_type})")

    p = Pipeline()
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
@click.option("--engine", default="auto", help="Transcription engine")
def batch(user_url, limit, engine):
    """Batch transcribe a creator's videos."""
    click.echo(f"Batch mode: {user_url} (limit={limit})")
    click.echo("Not yet implemented — use 'bp process' for single videos")

# ── Digest ──────────────────────────────────────────────────────

@cli.command()
@click.option("--sources", default="all", help="Sources to fetch (comma-separated or 'all')")
@click.option("--lang", default="en", help="Output language (en/zh/bilingual)")
@click.option("--days", default=1, type=int, help="Lookback days")
@click.option("--deliver", default=None, help="Delivery channels (comma-separated)")
@click.option("--skip-failed", is_flag=True, default=True, help="Skip failed sources")
@click.option("--no-state", is_flag=True, help="Ignore dedup state")
def digest(sources, lang, days, deliver, skip_failed, no_state):
    """Generate AI builder digest."""
    from builderpulse.sources.podcast import PodcastSource
    from builderpulse.sources.twitter import TwitterSource
    from builderpulse.sources.blog import BlogSource

    click.echo(f"Fetching content (last {days} days)...")

    items = []
    source_list = [s.strip() for s in sources.split(",")]

    if sources == "all" or "podcast" in source_list:
        try:
            src = PodcastSource()
            items.extend(src.fetch(days=days))
            click.echo(f"  Podcasts: {len(items)} items")
        except Exception as e:
            if not skip_failed:
                raise
            click.echo(f"  Podcasts: skipped ({e})", err=True)

    if sources == "all" or "twitter" in source_list:
        try:
            src = TwitterSource()
            tweets = src.fetch()
            items.extend(tweets)
            click.echo(f"  Twitter: {len(tweets)} items")
        except Exception as e:
            if not skip_failed:
                raise
            click.echo(f"  Twitter: skipped ({e})", err=True)

    if sources == "all" or "blog" in source_list:
        try:
            src = BlogSource()
            blogs = src.fetch(days=days)
            items.extend(blogs)
            click.echo(f"  Blogs: {len(blogs)} items")
        except Exception as e:
            if not skip_failed:
                raise
            click.echo(f"  Blogs: skipped ({e})", err=True)

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
        content = "\n\n".join(f"## {i.title}\n{i.content[:300]}\n{i.url}" for i in items[:20])
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
@click.argument("source", type=click.Choice(["twitter", "podcast", "blog", "bilibili", "youtube"]))
@click.option("--limit", default=10, help="Max items")
@click.option("--days", default=7, type=int, help="Lookback days")
@click.option("--user", default=None, help="User ID (for bilibili)")
def fetch(source, limit, days, user):
    """Fetch raw content from a source."""
    click.echo(f"Fetching from {source}...")

    if source == "podcast":
        from builderpulse.sources.podcast import PodcastSource
        items = PodcastSource().fetch(days=days, limit=limit)
    elif source == "twitter":
        from builderpulse.sources.twitter import TwitterSource
        items = TwitterSource().fetch(limit=limit)
    elif source == "blog":
        from builderpulse.sources.blog import BlogSource
        items = BlogSource().fetch(days=days, limit=limit)
    elif source == "bilibili":
        if not user:
            click.echo("Error: --user <mid> required for bilibili", err=True)
            sys.exit(1)
        from builderpulse.sources.bilibili import BilibiliSource
        items = BilibiliSource(users=[{"mid": int(user), "name": str(user)}]).fetch(limit=limit)
    elif source == "youtube":
        from builderpulse.sources.youtube import YouTubeSource
        items = YouTubeSource().fetch(limit=limit)
    else:
        click.echo(f"Unknown source: {source}")
        return

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
    from builderpulse.core.models import SourceRef
    from builderpulse.core.pipeline import Pipeline, step_download, step_transcribe, step_summarize, step_deliver

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
    """Set a configuration value."""
    click.echo(f"Set {key} = {value}")
    # TODO: persist to config file

@config.command("reload")
def config_reload():
    """Hot-reload configuration from file."""
    click.echo("Configuration reloaded")

# ── Serve (MCP) ─────────────────────────────────────────────────

@cli.command()
@click.option("--port", default=None, type=int, help="SSE port (default: stdio mode)")
def serve(port):
    """Start MCP server for AI agent integration."""
    os.environ["BUILDERPULSE_MODE"] = "mcp"
    click.echo("Starting BuilderPulse MCP server...", err=True)
    if port:
        click.echo(f"SSE mode on port {port}", err=True)
    else:
        click.echo("stdio mode", err=True)
    # TODO: actual MCP server startup

def main():
    cli()

if __name__ == "__main__":
    main()
