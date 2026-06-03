"""Migration from follow-builders and video2text to BuilderPulse."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from builderpulse.core.state import State, make_idem_key, make_idem_key_from_url

logger = logging.getLogger("builderpulse.migrate")


def migrate_follow_builders(state: State, source_dir: Path | str | None = None) -> dict:
    """Migrate from follow-builders state.json to BuilderPulse state.db."""
    source_dir = Path(source_dir) if source_dir else Path.home() / ".follow-builders"
    state_file = source_dir / "state.json"

    if not state_file.exists():
        logger.info(f"No follow-builders state found at {state_file}")
        return {"tweets": 0, "videos": 0, "articles": 0}

    data = json.loads(state_file.read_text(encoding="utf-8"))
    counts = {"tweets": 0, "videos": 0, "articles": 0}

    # Migrate seenTweets -> processed_items
    for tweet_id, timestamp_ms in data.get("seenTweets", {}).items():
        idem_key = make_idem_key("tweet", tweet_id)
        if not state.is_processed(idem_key):
            state.mark_processed(
                idem_key=idem_key,
                source_type="tweet",
                source_id=tweet_id,
                url=f"https://x.com/i/status/{tweet_id}",
                status="done",
            )
            counts["tweets"] += 1

    # Migrate seenArticles -> processed_items
    for url, timestamp_ms in data.get("seenArticles", {}).items():
        idem_key = make_idem_key_from_url(url)
        if not state.is_processed(idem_key):
            state.mark_processed(
                idem_key=idem_key,
                source_type="blog",
                source_id=url,
                url=url,
                status="done",
            )
            counts["articles"] += 1

    # Migrate seenVideos -> processed_items (podcast GUIDs)
    for guid, timestamp_ms in data.get("seenVideos", {}).items():
        idem_key = make_idem_key("podcast", guid)
        if not state.is_processed(idem_key):
            state.mark_processed(
                idem_key=idem_key,
                source_type="podcast",
                source_id=guid,
                url="",
                status="done",
            )
            counts["videos"] += 1

    logger.info(f"Migrated: {counts}")
    return counts


def migrate_video2text(state: State, source_dir: Path | str | None = None) -> dict:
    """Migrate from video2text output/ to BuilderPulse state.db."""
    source_dir = Path(source_dir) if source_dir else Path.home() / ".builderpulse" / "output"
    transcripts_dir = source_dir / "transcripts"

    if not transcripts_dir.exists():
        logger.info(f"No video2text transcripts found at {transcripts_dir}")
        return {"transcripts": 0}

    counts = {"transcripts": 0}

    for md_file in transcripts_dir.glob("*.md"):
        # Try to extract video ID from filename
        stem = md_file.stem
        # Pattern: {name}-{timestamp} or BV{id}
        if stem.startswith("BV"):
            bvid = stem.split("_")[0].split("-")[0]
            idem_key = make_idem_key("bilibili", bvid)
        else:
            idem_key = make_idem_key_from_url(stem)

        if not state.is_processed(idem_key):
            state.mark_processed(
                idem_key=idem_key,
                source_type="video",
                source_id=stem,
                url="",
                status="done",
                output_path=str(md_file),
            )
            counts["transcripts"] += 1

    logger.info(f"Migrated: {counts}")
    return counts


def migrate_all(
    state: State,
    follow_builders_dir: Path | str | None = None,
    video2text_dir: Path | str | None = None,
) -> dict:
    """Run all migrations."""
    result = {}
    result["follow_builders"] = migrate_follow_builders(state, follow_builders_dir)
    result["video2text"] = migrate_video2text(state, video2text_dir)
    return result
