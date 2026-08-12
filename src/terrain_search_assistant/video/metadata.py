"""Video metadata via ffprobe (no shell=True)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FfprobeError(RuntimeError):
    """Raised when ffprobe is missing or fails."""


@dataclass(frozen=True)
class VideoMetadata:
    duration_s: float | None
    width: int | None
    height: int | None
    fps: float | None
    codec: str | None


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "N/A"}:
        return None
    if "/" in rate:
        num_s, den_s = rate.split("/", 1)
        num = float(num_s)
        den = float(den_s)
        if den == 0:
            return None
        return num / den
    return float(rate)


def probe_video(path: Path) -> VideoMetadata:
    """Extract container/stream metadata using ffprobe."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"video file not found or moved: {path}")

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FfprobeError(
            "ffprobe not found on PATH. Install FFmpeg and ensure ffprobe is available."
        )

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise FfprobeError(
            f"ffprobe failed for {path}: {completed.stderr.strip() or 'unknown error'}"
        )

    payload = json.loads(completed.stdout)
    duration: float | None = None
    fmt = payload.get("format") or {}
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") != "video":
            continue
        width = int(stream["width"]) if stream.get("width") is not None else None
        height = int(stream["height"]) if stream.get("height") is not None else None
        codec = stream.get("codec_name")
        fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
        break

    return VideoMetadata(
        duration_s=duration,
        width=width,
        height=height,
        fps=fps,
        codec=codec,
    )
