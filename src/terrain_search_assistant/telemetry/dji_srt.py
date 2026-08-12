"""Robust DJI SRT telemetry parser."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from terrain_search_assistant.domain.models import TelemetrySample

_BLOCK_RE = re.compile(
    r"(?P<index>\d+)\s*\r?\n"
    r"(?P<start>\d{2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}[,\.]\d{1,3})\s*\r?\n"
    r"(?P<body>.*?)(?=(?:\r?\n)\d+\s*(?:\r?\n)|\Z)",
    re.DOTALL,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_KV_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*:\s*([^\s,\]]+)")
_LAT_RE = re.compile(r"(?:\[?\s*latitude\s*:\s*|lat\s*[:=]\s*)([+-]?\d+(?:\.\d+)?)", re.I)
_LON_RE = re.compile(r"(?:\[?\s*longitude\s*:\s*|lon\s*[:=]\s*|lng\s*[:=]\s*)([+-]?\d+(?:\.\d+)?)", re.I)
_LATLON_BRACKET_RE = re.compile(
    r"\[latitude:\s*([+-]?\d+(?:\.\d+)?)\]\s*\[longitude:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_GPS_PAREN_RE = re.compile(
    r"GPS\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)"
    r"(?:\s*,\s*([+-]?\d+(?:\.\d+)?))?\s*\)",
    re.IGNORECASE,
)
_ALT_RE = re.compile(
    r"\[rel_alt:\s*([+-]?\d+(?:\.\d+)?)\s+abs_alt:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_REL_ALT_RE = re.compile(r"(?:rel_alt|BAROMETER)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_ABS_ALT_RE = re.compile(r"abs_alt\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_GB_RE = re.compile(
    r"\[gb_yaw:\s*([+-]?\d+(?:\.\d+)?)\]\s*"
    r"\[gb_pitch:\s*([+-]?\d+(?:\.\d+)?)\]\s*"
    r"\[gb_roll:\s*([+-]?\d+(?:\.\d+)?)\]",
    re.IGNORECASE,
)
_YAW_RE = re.compile(r"(?:gb_yaw|yaw)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_PITCH_RE = re.compile(r"(?:gb_pitch|pitch)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_ROLL_RE = re.compile(r"(?:gb_roll|roll)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_ISO_RE = re.compile(
    r"(?:\bISO\s*(\d+)\b|\[?\s*iso\s*:\s*(\d+)\s*\]?)",
    re.IGNORECASE,
)
_SHUTTER_RE = re.compile(
    r"(?:\bShutter\s*[:\s]\s*([0-9./]+)|\[?\s*shutter\s*:\s*([0-9./]+)\s*\]?)",
    re.IGNORECASE,
)
_FNUM_RE = re.compile(
    r"(?:\bfnum\s*[:\s]\s*([0-9.]+)|\[?\s*fnum\s*:\s*([0-9.]+)\s*\]?|\bF/([0-9.]+))",
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


def _normalize_timecode(value: str) -> str:
    """Normalize ms part to 3 digits with comma separator."""
    match = re.match(r"(\d{2}:\d{2}:\d{2})[.,](\d{1,3})$", value.strip())
    if match is None:
        return value.strip()
    ms = (match.group(2) + "000")[:3]
    return f"{match.group(1)},{ms}"


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
    text = text.replace("\n", " ").replace("\r", " ")

    latitude: float | None = None
    longitude: float | None = None
    gps = _GPS_PAREN_RE.search(text)
    latlon = _LATLON_BRACKET_RE.search(text)
    if latlon:
        latitude = float(latlon.group(1))
        longitude = float(latlon.group(2))
    elif gps:
        latitude = float(gps.group(1))
        longitude = float(gps.group(2))
    else:
        lat_m = _LAT_RE.search(text)
        lon_m = _LON_RE.search(text)
        if lat_m:
            latitude = float(lat_m.group(1))
        if lon_m:
            longitude = float(lon_m.group(1))

    relative_altitude: float | None = None
    absolute_altitude: float | None = None
    alt = _ALT_RE.search(text)
    if alt:
        relative_altitude = float(alt.group(1))
        absolute_altitude = float(alt.group(2))
    else:
        rel_m = _REL_ALT_RE.search(text)
        abs_m = _ABS_ALT_RE.search(text)
        if rel_m:
            relative_altitude = float(rel_m.group(1))
        if abs_m:
            absolute_altitude = float(abs_m.group(1))
        if relative_altitude is None and gps is not None and gps.group(3):
            relative_altitude = float(gps.group(3))

    gimbal_yaw: float | None = None
    gimbal_pitch: float | None = None
    gimbal_roll: float | None = None
    gb = _GB_RE.search(text)
    if gb:
        gimbal_yaw = float(gb.group(1))
        gimbal_pitch = float(gb.group(2))
        gimbal_roll = float(gb.group(3))
    else:
        yaw_m = _YAW_RE.search(text)
        pitch_m = _PITCH_RE.search(text)
        roll_m = _ROLL_RE.search(text)
        if yaw_m:
            gimbal_yaw = float(yaw_m.group(1))
        if pitch_m:
            gimbal_pitch = float(pitch_m.group(1))
        if roll_m:
            gimbal_roll = float(roll_m.group(1))

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
        start_time=_normalize_timecode(start_tc),
        end_time=_normalize_timecode(end_tc),
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

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    samples: list[TelemetrySample] = []
    previous_start: float | None = None

    for match in _BLOCK_RE.finditer(normalized.strip() + "\n"):
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
        raise SrtParseError(
            "no SRT cue blocks found — проверьте, что файл в формате DJI SRT "
            "(нумерованные блоки с таймкодами 00:00:00,000 --> ...)"
        )
    return samples


def _decode_srt_bytes(raw: bytes) -> str:
    """Decode SRT bytes with common DJI/Windows encodings."""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    for encoding in ("utf-8", "utf-16", "utf-16-le", "cp1251", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        # Heuristic: a valid SRT should contain an arrow cue separator.
        if "-->" in text:
            return text
    return raw.decode("utf-8", errors="replace")


def parse_dji_srt_file(path: Path, *, max_bytes: int = 50 * 1024 * 1024) -> list[TelemetrySample]:
    """Parse a DJI SRT file with size guard and encoding fallbacks."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"SRT file not found: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise SrtParseError(
            f"SRT file too large ({size} bytes > limit {max_bytes}). "
            "Refusing unbounded load."
        )
    raw = path.read_bytes()
    content = _decode_srt_bytes(raw)
    return parse_dji_srt_text(content)
