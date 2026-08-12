"""Candidate evidence creation: screenshots, crops, typed records."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from terrain_search_assistant.domain.enums import CandidateCategory, EvidenceTag, ReviewStatus
from terrain_search_assistant.domain.models import BoundingBox, Candidate, TelemetrySample


def save_frame_jpeg(frame_bgr: NDArray[np.uint8], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame_bgr)
    if not ok:
        raise OSError(f"failed to write image: {path}")
    return path


def crop_frame(frame_bgr: NDArray[np.uint8], bbox: BoundingBox) -> NDArray[np.uint8]:
    h, w = frame_bgr.shape[:2]
    x1 = max(0, min(bbox.x, w - 1))
    y1 = max(0, min(bbox.y, h - 1))
    x2 = max(x1 + 1, min(bbox.x + bbox.width, w))
    y2 = max(y1 + 1, min(bbox.y + bbox.height, h))
    return frame_bgr[y1:y2, x1:x2].copy()


def build_candidate(
    *,
    operation_id: str,
    video_id: str,
    frame_index: int,
    timestamp_s: float,
    frame_bgr: NDArray[np.uint8],
    artifacts_dir: Path,
    category: CandidateCategory,
    evidence_tags: list[EvidenceTag],
    description: str,
    confidence: int,
    requires_reflight: bool,
    reflight_reason: str | None,
    bounding_box: BoundingBox | None = None,
    telemetry: TelemetrySample | None = None,
) -> Candidate:
    """Create candidate record and write screenshot/crop artifacts."""
    if not evidence_tags:
        raise ValueError("at least one evidence tag is required")
    if not description.strip():
        raise ValueError("description is required")
    if requires_reflight and not (reflight_reason and reflight_reason.strip()):
        raise ValueError("reflight_reason is required when requires_reflight is True")
    if not 1 <= confidence <= 5:
        raise ValueError("confidence must be 1..5")

    now = datetime.now(UTC)
    candidate_id_prefix = f"{video_id[:8]}_{frame_index}_{int(now.timestamp())}"
    screenshots_dir = artifacts_dir / "screenshots"
    crops_dir = artifacts_dir / "crops"
    screenshot_abs = screenshots_dir / f"{candidate_id_prefix}_full.jpg"
    save_frame_jpeg(frame_bgr, screenshot_abs)
    screenshot_rel = str(Path("artifacts/screenshots") / screenshot_abs.name)

    crop_rel: str | None = None
    if bounding_box is not None:
        crop = crop_frame(frame_bgr, bounding_box)
        crop_abs = crops_dir / f"{candidate_id_prefix}_crop.jpg"
        save_frame_jpeg(crop, crop_abs)
        crop_rel = str(Path("artifacts/crops") / crop_abs.name)

    return Candidate(
        operation_id=operation_id,
        video_id=video_id,
        frame_index=frame_index,
        timestamp_s=timestamp_s,
        drone_latitude=telemetry.latitude if telemetry else None,
        drone_longitude=telemetry.longitude if telemetry else None,
        estimated_target_geometry=None,
        uncertainty_radius_m=None,
        bounding_box=bounding_box,
        screenshot_path=screenshot_rel,
        crop_path=crop_rel,
        category=category,
        evidence_tags=evidence_tags,
        description=description.strip(),
        confidence=confidence,
        review_status=ReviewStatus.REVIEW_REQUIRED,
        requires_reflight=requires_reflight,
        reflight_reason=reflight_reason,
        created_at=now,
        updated_at=now,
        relative_altitude=telemetry.relative_altitude if telemetry else None,
        absolute_altitude=telemetry.absolute_altitude if telemetry else None,
        gimbal_yaw=telemetry.gimbal_yaw if telemetry else None,
        gimbal_pitch=telemetry.gimbal_pitch if telemetry else None,
        gimbal_roll=telemetry.gimbal_roll if telemetry else None,
        focal_length=telemetry.focal_length if telemetry else None,
        digital_zoom=telemetry.digital_zoom if telemetry else None,
    )
