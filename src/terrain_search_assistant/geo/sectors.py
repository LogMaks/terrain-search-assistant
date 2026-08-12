"""Search sector helpers: validation and aggregation."""

from __future__ import annotations

from typing import Any

from shapely.geometry import shape
from shapely.validation import explain_validity

from terrain_search_assistant.domain.models import AreaSummary, SearchSector
from terrain_search_assistant.geo.area import (
    geojson_area_m2,
    geojson_to_geometry,
    summarize_areas,
)


class SectorGeometryError(ValueError):
    """Invalid sector geometry."""


def validate_sector_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a GeoJSON geometry for a sector."""
    if "type" not in geojson:
        raise SectorGeometryError("GeoJSON must include type")

    geom_dict = geojson
    if geojson["type"] == "Feature":
        geom_dict = geojson.get("geometry") or {}
    if geom_dict.get("type") not in {"Polygon", "MultiPolygon"}:
        raise SectorGeometryError(
            f"sector geometry must be Polygon or MultiPolygon, got {geom_dict.get('type')}"
        )

    geom = shape(geom_dict)
    if not geom.is_valid:
        raise SectorGeometryError(f"invalid geometry: {explain_validity(geom)}")
    if geom.is_empty:
        raise SectorGeometryError("geometry is empty")

    # Ensure coordinate order awareness: GeoJSON is lon, lat.
    coords = list(geom.geoms[0].exterior.coords) if geom.geom_type == "MultiPolygon" else list(
        geom.exterior.coords
    )
    for lon, lat, *_rest in coords:
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise SectorGeometryError(
                f"coordinate out of range (expected lon,lat): ({lon}, {lat})"
            )

    return geom_dict


def compute_sector_area_m2(geojson: dict[str, Any]) -> float:
    validated = validate_sector_geojson(geojson)
    return geojson_area_m2(validated)


def summarize_sectors(
    sectors: list[SearchSector],
    *,
    overlap_warning_ratio: float = 0.1,
) -> AreaSummary:
    geoms = [geojson_to_geometry(s.geometry) for s in sectors]
    return summarize_areas(geoms, overlap_warning_ratio=overlap_warning_ratio)
