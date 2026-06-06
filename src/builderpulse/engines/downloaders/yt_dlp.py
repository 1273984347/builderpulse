"""yt-dlp based downloader for 1000+ sites."""

from __future__ import annotations

from pathlib import Path

from builderpulse.core.models import SourceRef, DownloadResult
from .base import Downloader


class YtDlpDownloader(Downloader):
    """Download videos using yt-dlp."""

    def can_handle(self, source: SourceRef) -> bool:
        return source.source_type in ("youtube", "web", "local")

    @property
    def name(self) -> str:
        return "yt-dlp"

    def download(self, source: SourceRef, output_dir: Path) -> DownloadResult:
        """Download video using yt-dlp."""
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import yt_dlp
        except ImportError:
            raise ImportError("yt-dlp not installed. Run: pip install yt-dlp")

        output_path = output_dir / f"{source.native_id}.mp4"

        ydl_opts = {
            "outtmpl": str(output_path),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source.url, download=True)
            title = info.get("title", source.title or "Unknown")
            duration = info.get("duration")

        # Find actual output file (yt-dlp may change extension)
        actual_path = self._find_output(output_dir, source.native_id)

        return DownloadResult(
            path=str(actual_path),
            source_type=source.source_type,
            native_id=source.native_id,
            title=title,
            duration=float(duration) if duration else None,
        )

    def _find_output(self, output_dir: Path, stem: str) -> Path:
        """Find the actual output file (yt-dlp may use different extension)."""
        for ext in (".mp4", ".mkv", ".webm", ".m4a"):
            p = output_dir / f"{stem}{ext}"
            if p.exists():
                return p
        # Fallback: return expected path
        return output_dir / f"{stem}.mp4"

    @staticmethod
    def _is_url(s: str) -> bool:
        return s.startswith("http://") or s.startswith("https://")
