"""Local video discovery and SRT pairing by stem."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


@dataclass(frozen=True)
class DiscoveredVideo:
    path: Path
    srt_path: Path | None
    filesize: int
    fingerprint: str


def compute_fingerprint(path: Path, *, head_bytes: int = 1024 * 1024) -> str:
    """Stable fingerprint without reading the entire multi-GB file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"video file not found: {path}")
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).encode("utf-8"))
    digest.update(str(stat.st_size).encode("utf-8"))
    digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
    with path.open("rb") as fh:
        digest.update(fh.read(head_bytes))
    return digest.hexdigest()


def discover_videos(directory: Path, *, recursive: bool = False) -> list[DiscoveredVideo]:
    """Find video files and optionally pair sibling .SRT/.srt by stem."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"directory not found: {directory}")

    pattern_iter = directory.rglob("*") if recursive else directory.iterdir()
    videos: list[Path] = []
    for path in pattern_iter:
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(path)

    results: list[DiscoveredVideo] = []
    for video in sorted(videos, key=lambda p: p.name.lower()):
        srt: Path | None = None
        for ext in (".SRT", ".srt"):
            candidate = video.with_suffix(ext)
            if candidate.is_file():
                srt = candidate
                break
        results.append(
            DiscoveredVideo(
                path=video,
                srt_path=srt,
                filesize=video.stat().st_size,
                fingerprint=compute_fingerprint(video),
            )
        )
    return results
