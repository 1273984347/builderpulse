"""Tests for Bilibili downloader."""

from builderpulse.core.models import SourceRef
from builderpulse.core.shared_utils import get_mixin_key
from builderpulse.engines.downloaders.bilibili import BilibiliDownloader


def test_can_handle():
    dl = BilibiliDownloader()
    bilibili = SourceRef(
        source_type="bilibili",
        native_id="BV123",
        url="https://bilibili.com/video/BV123",
    )
    assert dl.can_handle(bilibili)

    youtube = SourceRef(
        source_type="youtube",
        native_id="abc",
        url="https://yt.com",
    )
    assert not dl.can_handle(youtube)


def test_name():
    dl = BilibiliDownloader()
    assert dl.name == "bilibili"


def test_wbi_mixin_key():
    """Test the mixin key computation produces a 32-char string."""
    # Input must be at least 64 chars (enc tab indices go up to 63)
    raw = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    key = get_mixin_key(raw)
    assert len(key) == 32
    assert isinstance(key, str)
