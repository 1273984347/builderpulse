"""Tests for Douyin downloader."""
from builderpulse.core.models import SourceRef
from builderpulse.engines.downloaders.douyin import DouyinDownloader


def test_can_handle():
    dl = DouyinDownloader()
    douyin = SourceRef(source_type="douyin", native_id="abc", url="https://v.douyin.com/abc/")
    assert dl.can_handle(douyin)

    youtube = SourceRef(source_type="youtube", native_id="abc", url="https://yt.com")
    assert not dl.can_handle(youtube)


def test_name():
    dl = DouyinDownloader()
    assert dl.name == "douyin"
