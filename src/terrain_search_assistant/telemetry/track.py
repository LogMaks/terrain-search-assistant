"""Helpers to load telemetry bound to a video asset."""

from __future__ import annotations

from pathlib import Path

from terrain_search_assistant.config import DEFAULT_CONFIG, AppConfig
from terrain_search_assistant.domain.models import TelemetrySample, VideoAsset
from terrain_search_assistant.geo.bearing import telemetry_track_linestring
from terrain_search_assistant.telemetry.dji_srt import SrtParseError, parse_dji_srt_file


def load_bound_telemetry(
    video: VideoAsset,
    *,
    config: AppConfig | None = None,
) -> tuple[list[TelemetrySample], str | None]:
    """Load SRT samples for a video. Returns (samples, error_message)."""
    if not video.srt_path:
        return [], "SRT не привязан к видео"
    path = Path(video.srt_path)
    if not path.is_file():
        return [], f"SRT-файл недоступен: {path}"
    cfg = config or DEFAULT_CONFIG
    try:
        samples = parse_dji_srt_file(path, max_bytes=cfg.max_srt_bytes)
    except (SrtParseError, OSError) as exc:
        return [], str(exc)
    return samples, None


def gps_track_points(samples: list[TelemetrySample]) -> list[tuple[float, float]]:
    """Ordered (lon, lat) points with GPS present."""
    points: list[tuple[float, float]] = []
    for sample in samples:
        if sample.longitude is None or sample.latitude is None:
            continue
        points.append((float(sample.longitude), float(sample.latitude)))
    return points


def track_summary(samples: list[TelemetrySample]) -> dict[str, object]:
    """Compact stats for UI after SRT bind / track build."""
    points = gps_track_points(samples)
    line = telemetry_track_linestring(points)
    return {
        "samples_total": len(samples),
        "gps_points": len(points),
        "has_track": line is not None,
        "start": {"lon": points[0][0], "lat": points[0][1]} if points else None,
        "end": {"lon": points[-1][0], "lat": points[-1][1]} if points else None,
        "geojson": line,
    }


def list_srt_files(directory: Path, *, recursive: bool = False) -> list[Path]:
    """List .srt/.SRT files in a directory for manual binding."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"directory not found: {directory}")
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    files = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() == ".srt"
    ]
    return sorted(files, key=lambda p: p.name.lower())
