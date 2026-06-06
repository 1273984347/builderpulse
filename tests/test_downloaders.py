"""Tests for downloader base."""

from pathlib import Path

from builderpulse.core.models import SourceRef, DownloadResult
from builderpulse.engines.downloaders.base import Downloader


class MockDownloader(Downloader):
    def download(self, source: SourceRef, output_dir: Path) -> DownloadResult:
        return DownloadResult(
            path=str(output_dir / "test.mp4"),
            source_type=source.source_type,
            native_id=source.native_id,
            title="Test Video",
            duration=120.0,
        )

    def can_handle(self, source: SourceRef) -> bool:
        return source.source_type == "mock"

    @property
    def name(self) -> str:
        return "mock"


def test_downloader_interface():
    dl = MockDownloader()
    assert dl.name == "mock"


def test_can_handle():
    dl = MockDownloader()
    source = SourceRef(source_type="mock", native_id="123", url="http://test.com")
    assert dl.can_handle(source)

    other = SourceRef(source_type="youtube", native_id="abc", url="http://yt.com")
    assert not dl.can_handle(other)


def test_download():
    dl = MockDownloader()
    source = SourceRef(source_type="mock", native_id="123", url="http://test.com")
    result = dl.download(source, Path("/tmp"))
    assert result.path == str(Path("/tmp") / "test.mp4")
    assert result.duration == 120.0


def test_ytdlp_can_handle():
    from builderpulse.engines.downloaders.yt_dlp import YtDlpDownloader

    dl = YtDlpDownloader()
    assert dl.name == "yt-dlp"

    yt = SourceRef(
        source_type="youtube", native_id="abc", url="https://youtube.com/watch?v=abc"
    )
    assert dl.can_handle(yt)

    local = SourceRef(source_type="local", native_id="/f", url="/f.mp4")
    assert dl.can_handle(local)

    douyin = SourceRef(
        source_type="douyin", native_id="abc", url="https://douyin.com/abc"
    )
    assert not dl.can_handle(douyin)
