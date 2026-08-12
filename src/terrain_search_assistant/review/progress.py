"""Review progress helpers for grid cells and segments."""

from __future__ import annotations

from datetime import UTC, datetime

from terrain_search_assistant.domain.enums import FatigueWarningLevel, QualityIssue, ReviewStatus
from terrain_search_assistant.domain.models import ReviewSegment


def cell_labels(rows: int, cols: int) -> list[str]:
    return [f"R{r + 1}C{c + 1}" for r in range(rows) for c in range(cols)]


def build_segment(
    *,
    video_id: str,
    frame_index: int,
    fps: float,
    grid_cell: str | None,
    review_status: ReviewStatus,
    quality_issues: list[QualityIssue],
    operator_id: str,
    comment: str | None = None,
    fatigue_level: FatigueWarningLevel = FatigueWarningLevel.NONE,
) -> ReviewSegment:
    """Create a review segment for a single frame (or cell of a frame)."""
    issues = list(quality_issues)
    if fatigue_level == FatigueWarningLevel.HIGH_RISK and QualityIssue.FATIGUE_RISK not in issues:
        issues.append(QualityIssue.FATIGUE_RISK)

    ts = frame_index / fps if fps > 0 else float(frame_index)
    return ReviewSegment(
        video_id=video_id,
        start_timestamp_s=ts,
        end_timestamp_s=ts,
        start_frame=frame_index,
        end_frame=frame_index,
        grid_cell=grid_cell,
        review_status=review_status,
        quality_issues=issues,
        operator_id=operator_id,
        reviewed_at=datetime.now(UTC),
        comment=comment,
    )


def summarize_cell_statuses(
    segments: list[ReviewSegment],
    frame_index: int,
) -> dict[str, ReviewStatus]:
    """Latest status per grid cell for a given frame."""
    latest: dict[str, ReviewSegment] = {}
    for seg in segments:
        if seg.start_frame <= frame_index <= seg.end_frame and seg.grid_cell:
            prev = latest.get(seg.grid_cell)
            if prev is None or seg.reviewed_at >= prev.reviewed_at:
                latest[seg.grid_cell] = seg
    return {cell: seg.review_status for cell, seg in latest.items()}
