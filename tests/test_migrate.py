"""Tests for migration."""
import json

from builderpulse.core.state import State
from builderpulse.migrate import migrate_follow_builders, migrate_video2text


def test_migrate_follow_builders(tmp_path):
    """Test migrating follow-builders state.json."""
    # Create fake follow-builders state
    fb_dir = tmp_path / "follow-builders"
    fb_dir.mkdir()
    state_file = fb_dir / "state.json"
    state_file.write_text(json.dumps({
        "seenTweets": {"12345": 1700000000000, "67890": 1700000001000},
        "seenArticles": {"https://example.com/post1": 1700000002000},
        "seenVideos": {"guid-abc-123": 1700000003000},
    }))

    db_path = tmp_path / "state.db"
    state = State(db_path=db_path)

    result = migrate_follow_builders(state, fb_dir)
    assert result["tweets"] == 2
    assert result["articles"] == 1
    assert result["videos"] == 1

    # Verify items are in state
    assert state.is_processed("tweet:12345")
    assert state.is_processed("tweet:67890")
    state.close()


def test_migrate_follow_builders_no_file(tmp_path):
    """Test with no state.json."""
    db_path = tmp_path / "state.db"
    state = State(db_path=db_path)
    result = migrate_follow_builders(state, tmp_path / "nonexistent")
    assert result == {"tweets": 0, "videos": 0, "articles": 0}
    state.close()


def test_migrate_video2text(tmp_path):
    """Test migrating video2text transcripts."""
    v2t_dir = tmp_path / "output" / "transcripts"
    v2t_dir.mkdir(parents=True)
    (v2t_dir / "BV1Nd596vEyU-20260603.md").write_text("# Transcript\nHello world")
    (v2t_dir / "another_video-20260603.md").write_text("# Transcript\nAnother one")

    db_path = tmp_path / "state.db"
    state = State(db_path=db_path)

    result = migrate_video2text(state, tmp_path / "output")
    assert result["transcripts"] == 2
    assert state.is_processed("bilibili:BV1Nd596vEyU")
    state.close()


def test_migrate_idempotent(tmp_path):
    """Running migration twice should not duplicate entries."""
    fb_dir = tmp_path / "fb"
    fb_dir.mkdir()
    (fb_dir / "state.json").write_text(json.dumps({"seenTweets": {"111": 1700000000000}}))

    db_path = tmp_path / "state.db"
    state = State(db_path=db_path)

    r1 = migrate_follow_builders(state, fb_dir)
    r2 = migrate_follow_builders(state, fb_dir)
    assert r1["tweets"] == 1
    assert r2["tweets"] == 0  # Already migrated
    state.close()
