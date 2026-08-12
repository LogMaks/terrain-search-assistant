"""Robust DJI SRT telemetry parser."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from terrain_search_assistant.domain.models import TelemetrySample

_BLOCK_RE = re.compile(
    r"(?P<index>\d+)\s*\n"
    r"(?P<start>\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
    r"(?P<body>.*?)(?=\n\d+\s*\n|\Z)",
    re.DOTALL,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_KV_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*:\s*([^\s,]+)")
_LATLON_RE = re.compile(
    r"\[latitude:\s*([+-]?\d+(?:\.\d+)?)\]\s*\[longitude:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_ALT_RE = re.compile(
    r"\[rel_alt:\s*([+-]?\d+(?:\.\d+)?)\s+abs_alt:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_GB_RE = re.compile(
    r"\[gb_yaw:\s*([+-]?\d+(?:\.\d+)?)\]\s*"
    r"\[gb_pitch:\s*([+-]?\d+(?:\.\d+)?)\]\s*"
    r"\[gb_roll:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_ISO_RE = re.compile(
    r"(?:\bISO\s*(\d+)\b|\[?\s*iso\s*:\s*(\d+)\s*\]?)",
    re.IGNORECASE,
)
_SHUTTER_RE = re.compile(
    r"(?:\bShutter\s*[:\s]\s*([0-9./]+)|\[?\s*shutter\s*:\s*([0-9./]+)\s*\]?)",
    re.IGNORECASE,
)
_FNUM_RE = re.compile(
    r"(?:\bfnum\s*[:\s]\s*([0-9.]+)|\[?\s*fnum\s*:\s*([0-9.]+)\s*\]?)",
    re.IGNORECASE,
)
_FOCAL_RE = re.compile(
    r"(?:\bfocal_len\s*[:\s]\s*([0-9.]+)|\[?\s*focal_len\s*:\s*([0-9.]+)\s*\]?)",
    re.IGNORECASE,
)
_ZOOM_RE = re.compile(
    r"(?:\bdzoom_ratio\s*[:\s]\s*([0-9.]+)|\[?\s*dzoom_ratio\s*:\s*([0-9.]+)\s*\]?)",
    re.IGNORECASE,
)
_DATETIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)")


def _group_first(match: re.Match[str] | None) -> str | None:
    if match is None:
        return None
    for value in match.groups():
        if value is not None:
            return value
    return None


class SrtParseError(ValueError):
    """Raised when DJI SRT content is corrupt or invalid."""


def _parse_timecode(value: str) -> float:
    cleaned = value.replace(",", ".")
    hours, minutes, rest = cleaned.split(":")
    seconds = float(rest)
    return int(hours) * 3600 + int(minutes) * 60 + seconds


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_body(body: str, start_tc: str, end_tc: str, frame_index: int | None) -> TelemetrySample:
    text = _HTML_TAG_RE.sub(" ", body)
    text = text.replace("\n", " ")

    latitude: float | None = None
    longitude: float | None = None
    latlon = _LATLON_RE.search(text)
    if latlon:
        latitude = float(latlon.group(1))
        longitude = float(latlon.group(2))

    relative_altitude: float | None = None
    absolute_altitude: float | None = None
    alt = _ALT_RE.search(text)
    if alt:
        relative_altitude = float(alt.group(1))
        absolute_altitude = float(alt.group(2))

    gimbal_yaw: float | None = None
    gimbal_pitch: float | None = None
    gimbal_roll: float | None = None
    gb = _GB_RE.search(text)
    if gb:
        gimbal_yaw = float(gb.group(1))
        gimbal_pitch = float(gb.group(2))
        gimbal_roll = float(gb.group(3))

    iso_raw = _group_first(_ISO_RE.search(text))
    shutter_raw = _group_first(_SHUTTER_RE.search(text))
    fnum_raw = _group_first(_FNUM_RE.search(text))
    focal_raw = _group_first(_FOCAL_RE.search(text))
    zoom_raw = _group_first(_ZOOM_RE.search(text))
    dt_m = _DATETIME_RE.search(text)

    timestamp: datetime | None = None
    if dt_m:
        raw_dt = dt_m.group(1)
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                timestamp = datetime.strptime(raw_dt, fmt)
                break
            except ValueError:
                continue

    # Consume unknown key-value pairs without failing.
    _ = list(_KV_RE.finditer(text))

    return TelemetrySample(
        frame_index=frame_index,
        start_time=start_tc,
        end_time=end_tc,
        timestamp=timestamp,
        iso=int(iso_raw) if iso_raw is not None else None,
        shutter=shutter_raw,
        aperture=_to_float(fnum_raw),
        focal_length=_to_float(focal_raw),
        digital_zoom=_to_float(zoom_raw),
        latitude=latitude,
        longitude=longitude,
        relative_altitude=relative_altitude,
        absolute_altitude=absolute_altitude,
        gimbal_yaw=gimbal_yaw,
        gimbal_pitch=gimbal_pitch,
        gimbal_roll=gimbal_roll,
    )


def parse_dji_srt_text(content: str) -> list[TelemetrySample]:
    """Parse DJI SRT text into ordered TelemetrySample list."""
    if not content.strip():
        raise SrtParseError("SRT content is empty")

    samples: list[TelemetrySample] = []
    previous_start: float | None = None

    for match in _BLOCK_RE.finditer(content.strip() + "\n"):
        index = int(match.group("index"))
        start_tc = match.group("start")
        end_tc = match.group("end")
        body = match.group("body")
        start_s = _parse_timecode(start_tc)
        end_s = _parse_timecode(end_tc)
        if end_s < start_s:
            raise SrtParseError(f"block {index}: end time before start time")
        if previous_start is not None and start_s < previous_start:
            raise SrtParseError(f"block {index}: time order violation")
        previous_start = start_s
        try:
            sample = _parse_body(body, start_tc, end_tc, frame_index=index - 1)
        except ValueError as exc:
            raise SrtParseError(f"block {index}: {exc}") from exc
        samples.append(sample)

    if not samples:
        raise SrtParseError("no SRT cue blocks found")
    return samples


def parse_dji_srt_file(path: Path, *, max_bytes: int = 50 * 1024 * 1024) -> list[TelemetrySample]:
    """Parse a DJI SRT file with size guard."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"SRT file not found: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise SrtParseError(
            f"SRT file too large ({size} bytes > limit {max_bytes}). "
            "Refusing unbounded load."
        )
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_dji_srt_text(content)
