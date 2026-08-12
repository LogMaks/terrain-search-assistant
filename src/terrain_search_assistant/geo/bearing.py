"""Bearing / approximate camera look-direction helpers."""

from __future__ import annotations

from dataclasses import dataclass

from pyproj import Geod

WGS84_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class VisirLine:
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    length_m: float
    yaw_deg: float


def destination_point(
    lon: float,
    lat: float,
    azimuth_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    """Compute destination using geodesic forward. Returns (lon, lat)."""
    if distance_m <= 0:
        raise ValueError("distance_m must be positive")
    end_lon, end_lat, _back = WGS84_GEOD.fwd(lon, lat, azimuth_deg, distance_m)
    return float(end_lon), float(end_lat)


def build_visir_line(
    longitude: float,
    latitude: float,
    gimbal_yaw: float,
    *,
    length_m: float = 1000.0,
) -> VisirLine:
    """Approximate look-direction ray from drone position using gimbal yaw."""
    end_lon, end_lat = destination_point(longitude, latitude, gimbal_yaw, length_m)
    return VisirLine(
        start_lon=longitude,
        start_lat=latitude,
        end_lon=end_lon,
        end_lat=end_lat,
        length_m=length_m,
        yaw_deg=gimbal_yaw,
    )


def telemetry_track_linestring(
    points: list[tuple[float, float]],
) -> dict[str, object] | None:
    """Build GeoJSON LineString from (lon, lat) pairs. Returns None if <2 points."""
    if len(points) < 2:
        return None
    return {
        "type": "LineString",
        "coordinates": [[lon, lat] for lon, lat in points],
    }
