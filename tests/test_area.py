"""Geodesic area tests. Coordinates are synthetic, not operational."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from terrain_search_assistant.geo.area import geometry_area_m2, summarize_areas


def _square(lon: float, lat: float, d: float = 0.01) -> Polygon:
    # GeoJSON / Shapely order: lon, lat
    return box(lon, lat, lon + d, lat + d)


def test_single_sector_positive_area() -> None:
    poly = _square(9.0, 46.0)
    area = geometry_area_m2(poly)
    assert area > 0


def test_two_non_overlapping() -> None:
    a = _square(9.0, 46.0)
    b = _square(9.05, 46.0)
    summary = summarize_areas([a, b])
    assert summary.overlap_m2 == pytest.approx(0.0, abs=1.0)
    assert summary.union_m2 == pytest.approx(summary.sum_individual_m2, rel=1e-3)


def test_two_overlapping() -> None:
    a = _square(9.0, 46.0, 0.02)
    b = _square(9.01, 46.0, 0.02)
    summary = summarize_areas([a, b])
    assert summary.overlap_m2 > 0
    assert summary.union_m2 < summary.sum_individual_m2
    assert summary.has_substantial_overlap


def test_multipolygon() -> None:
    from shapely.geometry import MultiPolygon

    mp = MultiPolygon([_square(9.0, 46.0), _square(9.1, 46.1)])
    area = geometry_area_m2(mp)
    assert area > geometry_area_m2(_square(9.0, 46.0))


def test_polygon_with_hole() -> None:
    outer = [(9.0, 46.0), (9.02, 46.0), (9.02, 46.02), (9.0, 46.02), (9.0, 46.0)]
    hole = [(9.005, 46.005), (9.015, 46.005), (9.015, 46.015), (9.005, 46.015), (9.005, 46.005)]
    poly = Polygon(outer, [hole])
    solid = Polygon(outer)
    assert geometry_area_m2(poly) < geometry_area_m2(solid)


def test_lon_lat_order_matters() -> None:
    # Correct lon,lat near Alps
    correct = Polygon([(9.0, 46.0), (9.01, 46.0), (9.01, 46.01), (9.0, 46.01), (9.0, 46.0)])
    # Swapped would be invalid / nonsense for this region
    swapped = Polygon([(46.0, 9.0), (46.01, 9.0), (46.01, 9.01), (46.0, 9.01), (46.0, 9.0)])
    a_correct = geometry_area_m2(correct)
    a_swapped = geometry_area_m2(swapped)
    assert a_correct != pytest.approx(a_swapped, rel=0.01)
