"""Bearing / visir tests."""

from __future__ import annotations

import pytest

from terrain_search_assistant.geo.bearing import (
    build_visir_line,
    destination_point,
    telemetry_track_linestring,
)


def test_destination_north() -> None:
    lon, lat = destination_point(0.0, 0.0, 0.0, 1000.0)
    assert lon == pytest.approx(0.0, abs=1e-5)
    assert lat > 0


def test_visir_line_length() -> None:
    line = build_visir_line(9.0, 46.0, 90.0, length_m=1000.0)
    assert line.end_lon > line.start_lon
    assert line.length_m == 1000.0


def test_track_linestring() -> None:
    assert telemetry_track_linestring([(9.0, 46.0)]) is None
    geo = telemetry_track_linestring([(9.0, 46.0), (9.1, 46.1)])
    assert geo is not None
    assert geo["type"] == "LineString"
    assert geo["coordinates"][0] == [9.0, 46.0]
