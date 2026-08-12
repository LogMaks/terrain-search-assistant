"""Future DEM / visibility interfaces. No fake coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class CameraPose:
    """Camera pose in geographic / local frames. DEM required for ground projection."""

    longitude: float
    latitude: float
    altitude_m: float | None
    yaw_deg: float | None
    pitch_deg: float | None
    roll_deg: float | None
    focal_length_mm: float | None = None
    digital_zoom: float | None = None


@dataclass(frozen=True)
class CentralRay:
    origin_lon: float
    origin_lat: float
    origin_alt_m: float | None
    azimuth_deg: float
    elevation_deg: float | None


@dataclass(frozen=True)
class RayTerrainIntersection:
    """Result of ray–DEM intersection. Not implemented in this iteration."""

    longitude: float
    latitude: float
    altitude_m: float
    distance_m: float


@dataclass(frozen=True)
class CameraFrustum:
    """Camera frustum description placeholder."""

    pose: CameraPose
    hfov_deg: float | None
    vfov_deg: float | None


@dataclass(frozen=True)
class TerrainFootprint:
    """Projected ground footprint. Requires DEM."""

    geojson: dict[str, object]


@dataclass(frozen=True)
class ViewshedResult:
    """Occlusion / viewshed analysis placeholder."""

    geojson: dict[str, object]


@dataclass(frozen=True)
class GroundSamplingDistance:
    """Estimated GSD at a ground point."""

    meters_per_pixel: float


@dataclass(frozen=True)
class ProbabilisticCoverage:
    """Probabilistic coverage map metadata."""

    note: str


@dataclass(frozen=True)
class UncertaintyEstimate:
    """Spatial uncertainty for a candidate projection."""

    radius_m: float
    method: str


class DemLoader(Protocol):
    def load(self, path: Path) -> NDArray[np.floating]:
        """Load a DEM raster. Not implemented in this iteration."""
        ...


def load_dem(path: Path) -> NDArray[np.floating]:
    """Load DEM elevation grid.

    Raises:
        NotImplementedError: DEM loading is out of scope for iteration 1.
    """
    raise NotImplementedError(
        f"DEM loading is not implemented in this iteration (requested: {path}). "
        "Do not invent elevation or ground coordinates."
    )


def build_central_ray(pose: CameraPose) -> CentralRay:
    """Build approximate central optical ray from camera pose."""
    if pose.yaw_deg is None:
        raise ValueError("yaw is required to build a central ray")
    return CentralRay(
        origin_lon=pose.longitude,
        origin_lat=pose.latitude,
        origin_alt_m=pose.altitude_m,
        azimuth_deg=pose.yaw_deg,
        elevation_deg=pose.pitch_deg,
    )


def intersect_ray_with_terrain(
    ray: CentralRay,
    dem: NDArray[np.floating],
) -> RayTerrainIntersection:
    """Intersect camera ray with DEM.

    Raises:
        NotImplementedError: exact ray–terrain intersection needs DEM plumbing.
    """
    raise NotImplementedError(
        "Ray–terrain intersection is not implemented. "
        f"Refusing to invent ground coordinates for ray from "
        f"({ray.origin_lon}, {ray.origin_lat}); dem shape={dem.shape}."
    )


def camera_frustum(
    pose: CameraPose,
    hfov_deg: float | None,
    vfov_deg: float | None,
) -> CameraFrustum:
    """Describe camera frustum (metadata only until DEM is available)."""
    return CameraFrustum(pose=pose, hfov_deg=hfov_deg, vfov_deg=vfov_deg)


def terrain_footprint(frustum: CameraFrustum, dem: NDArray[np.floating]) -> TerrainFootprint:
    """Project camera frustum onto terrain.

    Raises:
        NotImplementedError: footprint requires DEM and camera intrinsics.
    """
    raise NotImplementedError(
        "Terrain footprint is not implemented without DEM intersection. "
        f"frustum pose=({frustum.pose.longitude}, {frustum.pose.latitude}), dem={dem.shape}."
    )


def compute_viewshed(pose: CameraPose, dem: NDArray[np.floating]) -> ViewshedResult:
    """Compute occlusion / viewshed.

    Raises:
        NotImplementedError: viewshed requires DEM.
    """
    raise NotImplementedError(
        "Viewshed/occlusion is not implemented without DEM. "
        f"pose=({pose.longitude}, {pose.latitude}), dem={dem.shape}."
    )


def estimate_gsd(
    pose: CameraPose,
    ground_distance_m: float,
    sensor_width_mm: float,
    image_width_px: int,
) -> GroundSamplingDistance:
    """Estimate ground sampling distance for a known ground distance.

    Raises:
        NotImplementedError: reliable GSD needs verified altitude above terrain.
    """
    raise NotImplementedError(
        "GSD estimation is not implemented without verified height above terrain. "
        f"inputs: distance={ground_distance_m}, sensor={sensor_width_mm}, "
        f"width={image_width_px}, pose_alt={pose.altitude_m}."
    )


def probabilistic_coverage(sectors_geojson: list[dict[str, object]]) -> ProbabilisticCoverage:
    """Probabilistic coverage model.

    Raises:
        NotImplementedError: coverage probability needs footprint + viewshed.
    """
    raise NotImplementedError(
        "Probabilistic coverage is not implemented. "
        f"Received {len(sectors_geojson)} sector geometries; no DEM coverage model available."
    )


def candidate_ray_intersection(
    pose: CameraPose,
    pixel_x: float,
    pixel_y: float,
    image_width: int,
    image_height: int,
    dem: NDArray[np.floating],
) -> RayTerrainIntersection:
    """Project a candidate pixel through the camera onto DEM.

    Raises:
        NotImplementedError: pixel projection needs intrinsics + DEM.
    """
    raise NotImplementedError(
        "Candidate ray intersection is not implemented. "
        "Do not treat drone coordinates as object coordinates. "
        f"pixel=({pixel_x}, {pixel_y}) image=({image_width}x{image_height}) "
        f"pose=({pose.longitude}, {pose.latitude}) dem={dem.shape}."
    )


def estimate_uncertainty(
    pose: CameraPose,
    intersection: RayTerrainIntersection | None = None,
) -> UncertaintyEstimate:
    """Estimate spatial uncertainty for a projected candidate.

    Raises:
        NotImplementedError: uncertainty model requires DEM intersection.
    """
    raise NotImplementedError(
        "Uncertainty estimation is not implemented without DEM intersection. "
        f"pose=({pose.longitude}, {pose.latitude}), intersection={intersection}."
    )
