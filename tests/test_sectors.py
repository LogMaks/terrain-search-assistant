"""Sector validation and area aggregation."""

from __future__ import annotations

import pytest

from terrain_search_assistant.domain.enums import SectorPriority, SectorStatus
from terrain_search_assistant.domain.models import SearchSector
from terrain_search_assistant.geo.sectors import (
    SectorGeometryError,
    compute_sector_area_m2,
    summarize_sectors,
    validate_sector_geojson,
)


def test_validate_polygon() -> None:
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[9.0, 46.0], [9.01, 46.0], [9.01, 46.01], [9.0, 46.01], [9.0, 46.0]]
        ],
    }
    validated = validate_sector_geojson(geom)
    assert validated["type"] == "Polygon"
    assert compute_sector_area_m2(validated) > 0


def test_reject_point() -> None:
    with pytest.raises(SectorGeometryError):
        validate_sector_geojson({"type": "Point", "coordinates": [9.0, 46.0]})


def test_summarize_sectors() -> None:
    g1 = {
        "type": "Polygon",
        "coordinates": [
            [[9.0, 46.0], [9.02, 46.0], [9.02, 46.02], [9.0, 46.02], [9.0, 46.0]]
        ],
    }
    g2 = {
        "type": "Polygon",
        "coordinates": [
            [[9.01, 46.0], [9.03, 46.0], [9.03, 46.02], [9.01, 46.02], [9.01, 46.0]]
        ],
    }
    sectors = [
        SearchSector(
            operation_id="op",
            name="A",
            priority=SectorPriority.HIGH,
            status=SectorStatus.PLANNED,
            geometry=g1,
            area_m2=compute_sector_area_m2(g1),
        ),
        SearchSector(
            operation_id="op",
            name="B",
            priority=SectorPriority.MEDIUM,
            status=SectorStatus.PLANNED,
            geometry=g2,
            area_m2=compute_sector_area_m2(g2),
        ),
    ]
    summary = summarize_sectors(sectors)
    assert summary.overlap_m2 > 0
    assert summary.union_m2 < summary.sum_individual_m2
