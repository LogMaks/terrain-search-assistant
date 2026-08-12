"""Typed domain models. Unknown values stay None — never fake zeros/coords."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from terrain_search_assistant.domain.enums import (
    CandidateCategory,
    EvidenceTag,
    FatigueWarningLevel,
    IndexingStatus,
    OperationStatus,
    QualityIssue,
    ReviewStatus,
    SectorPriority,
    SectorStatus,
    SessionState,
)


def new_id() -> str:
    return str(uuid4())


class SearchOperation(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    created_at: datetime
    updated_at: datetime
    status: OperationStatus = OperationStatus.DRAFT
    comment: str | None = None


class SearchSector(BaseModel):
    id: str = Field(default_factory=new_id)
    operation_id: str
    name: str
    priority: SectorPriority = SectorPriority.MEDIUM
    status: SectorStatus = SectorStatus.PLANNED
    geometry: dict[str, Any]
    area_m2: float = Field(ge=0.0)
    comment: str | None = None
    requires_reflight: bool = False
    reflight_reason: str | None = None

    @model_validator(mode="after")
    def _reflight_reason_required(self) -> SearchSector:
        if self.requires_reflight and not (self.reflight_reason and self.reflight_reason.strip()):
            raise ValueError("reflight_reason is required when requires_reflight is True")
        return self


class VideoAsset(BaseModel):
    id: str = Field(default_factory=new_id)
    operation_id: str
    path: str
    filename: str
    filesize: int | None = None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    srt_path: str | None = None
    indexing_status: IndexingStatus = IndexingStatus.PENDING
    fingerprint: str | None = None


class TelemetrySample(BaseModel):
    frame_index: int | None = None
    start_time: str
    end_time: str
    timestamp: datetime | None = None
    iso: int | None = None
    shutter: str | None = None
    aperture: float | None = None
    focal_length: float | None = None
    digital_zoom: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    relative_altitude: float | None = None
    absolute_altitude: float | None = None
    gimbal_yaw: float | None = None
    gimbal_pitch: float | None = None
    gimbal_roll: float | None = None

    @field_validator("latitude")
    @classmethod
    def _lat_range(cls, value: float | None) -> float | None:
        if value is not None and not (-90.0 <= value <= 90.0):
            raise ValueError(f"latitude out of range: {value}")
        return value

    @field_validator("longitude")
    @classmethod
    def _lon_range(cls, value: float | None) -> float | None:
        if value is not None and not (-180.0 <= value <= 180.0):
            raise ValueError(f"longitude out of range: {value}")
        return value


class ReviewSession(BaseModel):
    id: str = Field(default_factory=new_id)
    operation_id: str
    video_id: str
    operator_name: str
    started_at: datetime
    ended_at: datetime | None = None
    active_duration_s: float = 0.0
    pause_duration_s: float = 0.0
    state: SessionState = SessionState.IDLE
    fatigue_warning_level: FatigueWarningLevel = FatigueWarningLevel.NONE


class BoundingBox(BaseModel):
    """Normalized or pixel bbox for a frame region. Coordinates in pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ReviewSegment(BaseModel):
    id: str = Field(default_factory=new_id)
    video_id: str
    start_timestamp_s: float
    end_timestamp_s: float
    start_frame: int
    end_frame: int
    grid_cell: str | None = None
    review_status: ReviewStatus
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    operator_id: str
    reviewed_at: datetime
    comment: str | None = None


class Candidate(BaseModel):
    id: str = Field(default_factory=new_id)
    operation_id: str
    video_id: str
    frame_index: int = Field(ge=0)
    timestamp_s: float
    drone_latitude: float | None = None
    drone_longitude: float | None = None
    estimated_target_geometry: dict[str, Any] | None = None
    uncertainty_radius_m: float | None = None
    bounding_box: BoundingBox | None = None
    screenshot_path: str
    crop_path: str | None = None
    category: CandidateCategory
    evidence_tags: list[EvidenceTag]
    description: str
    confidence: int = Field(ge=1, le=5)
    review_status: ReviewStatus = ReviewStatus.REVIEW_REQUIRED
    requires_reflight: bool = False
    reflight_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    # Telemetry snapshot for audit (optional extras)
    relative_altitude: float | None = None
    absolute_altitude: float | None = None
    gimbal_yaw: float | None = None
    gimbal_pitch: float | None = None
    gimbal_roll: float | None = None
    focal_length: float | None = None
    digital_zoom: float | None = None

    @model_validator(mode="after")
    def _validate_candidate(self) -> Candidate:
        if not self.evidence_tags:
            raise ValueError("at least one evidence tag is required")
        if not self.description.strip():
            raise ValueError("description is required")
        if self.requires_reflight and not (self.reflight_reason and self.reflight_reason.strip()):
            raise ValueError("reflight_reason is required when requires_reflight is True")
        return self


class AreaSummary(BaseModel):
    sum_individual_m2: float
    union_m2: float
    overlap_m2: float
    overlap_ratio: float
    has_substantial_overlap: bool
