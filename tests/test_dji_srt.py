"""Tests for DJI SRT parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from terrain_search_assistant.telemetry.dji_srt import (
    SrtParseError,
    parse_dji_srt_file,
    parse_dji_srt_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_dji.srt"


def test_parse_fixture_samples() -> None:
    samples = parse_dji_srt_file(FIXTURE)
    assert len(samples) == 4
    assert samples[0].latitude == pytest.approx(46.812345)
    assert samples[0].longitude == pytest.approx(9.123456)
    assert samples[0].gimbal_yaw == pytest.approx(45.0)
    assert samples[0].focal_length == pytest.approx(24.0)
    assert samples[3].latitude is None
    assert samples[3].longitude is None


def test_time_order_violation() -> None:
    bad = """1
00:00:01,000 --> 00:00:01,033
a

2
00:00:00,500 --> 00:00:00,533
b
"""
    with pytest.raises(SrtParseError, match="time order"):
        parse_dji_srt_text(bad)


def test_invalid_latitude() -> None:
    bad = """1
00:00:00,000 --> 00:00:00,033
[latitude: 120.0] [longitude: 9.0]
"""
    with pytest.raises(SrtParseError):
        parse_dji_srt_text(bad)


def test_size_guard(tmp_path: Path) -> None:
    huge = tmp_path / "huge.srt"
    huge.write_text("x" * 1000)
    with pytest.raises(SrtParseError, match="too large"):
        parse_dji_srt_file(huge, max_bytes=100)


def test_parse_gps_paren_and_crlf() -> None:
    content = (
        "1\r\n"
        "00:00:00.000 --> 00:00:00.033\r\n"
        "F/2.8, SS 100, ISO100 GPS (46.500000, 9.250000, 120.5) "
        "gb_yaw: 10.0 gb_pitch: -20.0 gb_roll: 0.0\r\n"
        "\r\n"
        "2\r\n"
        "00:00:00.033 --> 00:00:00.066\r\n"
        "GPS (46.500100, 9.250100)\r\n"
    )
    samples = parse_dji_srt_text(content)
    assert len(samples) == 2
    assert samples[0].latitude == pytest.approx(46.5)
    assert samples[0].longitude == pytest.approx(9.25)
    assert samples[0].relative_altitude == pytest.approx(120.5)
    assert samples[0].gimbal_yaw == pytest.approx(10.0)


def test_utf16_srt_file(tmp_path: Path) -> None:
    content = """1
00:00:00,000 --> 00:00:00,033
[latitude: 46.1] [longitude: 9.2]
[gb_yaw: 1.0] [gb_pitch: -2.0] [gb_roll: 0.0]
"""
    path = tmp_path / "utf16.srt"
    path.write_bytes(content.encode("utf-16"))
    samples = parse_dji_srt_file(path)
    assert len(samples) == 1
    assert samples[0].latitude == pytest.approx(46.1)
