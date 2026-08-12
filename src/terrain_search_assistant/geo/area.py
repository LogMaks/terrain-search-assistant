"""Geodesic area calculations. Never use Shapely.area in EPSG:4326."""

from __future__ import annotations

from typing import Any

from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from terrain_search_assistant.domain.models import AreaSummary

WGS84_GEOD = Geod(ellps="WGS84")


def geojson_to_geometry(geojson: dict[str, Any]) -> BaseGeometry:
    """Convert GeoJSON geometry/feature to a valid Shapely geometry."""
    if geojson.get("type") == "Feature":
        geom_obj = geojson.get("geometry")
        if not isinstance(geom_obj, dict):
            raise ValueError("Feature.geometry must be a GeoJSON geometry object")
        geom = shape(geom_obj)
    elif geojson.get("type") == "FeatureCollection":
        features = geojson.get("features") or []
        geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
        if not geoms:
            raise ValueError("FeatureCollection has no geometries")
        geom = unary_union(geoms)
    else:
        geom = shape(geojson)

    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        raise ValueError("geometry is empty")
    return geom


def geometry_area_m2(geom: BaseGeometry) -> float:
    """Absolute geodesic area in square meters.

    Polygons with holes are computed as exterior area minus hole areas,
    because signed-area aggregation via abs() alone can overcount holes.
    """
    if geom.geom_type == "Polygon":
        exterior_area, _ = WGS84_GEOD.geometry_area_perimeter(geom.exterior)
        total = abs(float(exterior_area))
        for ring in geom.interiors:
            hole_area, _ = WGS84_GEOD.geometry_area_perimeter(ring)
            total -= abs(float(hole_area))
        return max(0.0, total)
    if geom.geom_type == "MultiPolygon":
        return float(sum(geometry_area_m2(part) for part in geom.geoms))
    area, _perimeter = WGS84_GEOD.geometry_area_perimeter(geom)
    return abs(float(area))


def geojson_area_m2(geojson: dict[str, Any]) -> float:
    return geometry_area_m2(geojson_to_geometry(geojson))


def format_area(area_m2: float) -> dict[str, float]:
    return {
        "m2": area_m2,
        "ha": area_m2 / 10_000.0,
        "km2": area_m2 / 1_000_000.0,
    }


def summarize_areas(
    geometries: list[BaseGeometry],
    *,
    overlap_warning_ratio: float = 0.1,
) -> AreaSummary:
    """Sum, union, and overlap of search sectors."""
    if not geometries:
        return AreaSummary(
            sum_individual_m2=0.0,
            union_m2=0.0,
            overlap_m2=0.0,
            overlap_ratio=0.0,
            has_substantial_overlap=False,
        )

    individuals = [geometry_area_m2(g) for g in geometries]
    sum_individual = float(sum(individuals))
    union_geom = unary_union(geometries)
    union_m2 = geometry_area_m2(union_geom)
    overlap_m2 = max(0.0, sum_individual - union_m2)
    overlap_ratio = (overlap_m2 / sum_individual) if sum_individual > 0 else 0.0
    return AreaSummary(
        sum_individual_m2=sum_individual,
        union_m2=union_m2,
        overlap_m2=overlap_m2,
        overlap_ratio=overlap_ratio,
        has_substantial_overlap=overlap_ratio >= overlap_warning_ratio,
    )


def geometry_to_geojson(geom: BaseGeometry) -> dict[str, Any]:
    result = mapping(geom)
    if not isinstance(result, dict):
        raise TypeError("unexpected mapping result")
    return result
