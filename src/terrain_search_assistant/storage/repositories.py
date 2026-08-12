"""Repository layer over SQLite. Errors are never swallowed."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

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
from terrain_search_assistant.domain.models import (
    BoundingBox,
    Candidate,
    ReviewSegment,
    ReviewSession,
    SearchOperation,
    SearchSector,
    VideoAsset,
)
from terrain_search_assistant.storage.database import Database


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class OperationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, operation: SearchOperation) -> SearchOperation:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO operations(id, name, created_at, updated_at, status, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    operation.id,
                    operation.name,
                    _dt(operation.created_at),
                    _dt(operation.updated_at),
                    operation.status.value,
                    operation.comment,
                ),
            )
        return operation

    def update(self, operation: SearchOperation) -> SearchOperation:
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE operations
                SET name = ?, updated_at = ?, status = ?, comment = ?
                WHERE id = ?
                """,
                (
                    operation.name,
                    _dt(operation.updated_at),
                    operation.status.value,
                    operation.comment,
                    operation.id,
                ),
            )
        return operation

    def get(self, operation_id: str) -> SearchOperation | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE id = ?", (operation_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> list[SearchOperation]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM operations ORDER BY created_at DESC"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: Any) -> SearchOperation:
        return SearchOperation(
            id=row["id"],
            name=row["name"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            status=OperationStatus(row["status"]),
            comment=row["comment"],
        )


class SectorRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, sector: SearchSector) -> SearchSector:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sectors(
                    id, operation_id, name, priority, status, geometry_json,
                    area_m2, comment, requires_reflight, reflight_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sector.id,
                    sector.operation_id,
                    sector.name,
                    sector.priority.value,
                    sector.status.value,
                    json.dumps(sector.geometry),
                    sector.area_m2,
                    sector.comment,
                    int(sector.requires_reflight),
                    sector.reflight_reason,
                ),
            )
        return sector

    def list_for_operation(self, operation_id: str) -> list[SearchSector]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM sectors WHERE operation_id = ? ORDER BY name",
                (operation_id,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def delete(self, sector_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM sectors WHERE id = ?", (sector_id,))

    def get(self, sector_id: str) -> SearchSector | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM sectors WHERE id = ?", (sector_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: Any) -> SearchSector:
        return SearchSector(
            id=row["id"],
            operation_id=row["operation_id"],
            name=row["name"],
            priority=SectorPriority(row["priority"]),
            status=SectorStatus(row["status"]),
            geometry=json.loads(row["geometry_json"]),
            area_m2=float(row["area_m2"]),
            comment=row["comment"],
            requires_reflight=bool(row["requires_reflight"]),
            reflight_reason=row["reflight_reason"],
        )


class VideoRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, video: VideoAsset) -> VideoAsset:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO videos(
                    id, operation_id, path, filename, filesize, duration_s,
                    width, height, fps, codec, srt_path, indexing_status, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    path=excluded.path,
                    filename=excluded.filename,
                    filesize=excluded.filesize,
                    duration_s=excluded.duration_s,
                    width=excluded.width,
                    height=excluded.height,
                    fps=excluded.fps,
                    codec=excluded.codec,
                    srt_path=excluded.srt_path,
                    indexing_status=excluded.indexing_status,
                    fingerprint=excluded.fingerprint
                """,
                (
                    video.id,
                    video.operation_id,
                    video.path,
                    video.filename,
                    video.filesize,
                    video.duration_s,
                    video.width,
                    video.height,
                    video.fps,
                    video.codec,
                    video.srt_path,
                    video.indexing_status.value,
                    video.fingerprint,
                ),
            )
        return video

    def list_for_operation(self, operation_id: str) -> list[VideoAsset]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM videos WHERE operation_id = ? ORDER BY filename",
                (operation_id,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def get(self, video_id: str) -> VideoAsset | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM videos WHERE id = ?", (video_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: Any) -> VideoAsset:
        return VideoAsset(
            id=row["id"],
            operation_id=row["operation_id"],
            path=row["path"],
            filename=row["filename"],
            filesize=row["filesize"],
            duration_s=row["duration_s"],
            width=row["width"],
            height=row["height"],
            fps=row["fps"],
            codec=row["codec"],
            srt_path=row["srt_path"],
            indexing_status=IndexingStatus(row["indexing_status"]),
            fingerprint=row["fingerprint"],
        )


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, session: ReviewSession) -> ReviewSession:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO review_sessions(
                    id, operation_id, video_id, operator_name, started_at, ended_at,
                    active_duration_s, pause_duration_s, state, fatigue_warning_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    ended_at=excluded.ended_at,
                    active_duration_s=excluded.active_duration_s,
                    pause_duration_s=excluded.pause_duration_s,
                    state=excluded.state,
                    fatigue_warning_level=excluded.fatigue_warning_level
                """,
                (
                    session.id,
                    session.operation_id,
                    session.video_id,
                    session.operator_name,
                    _dt(session.started_at),
                    _dt(session.ended_at) if session.ended_at else None,
                    session.active_duration_s,
                    session.pause_duration_s,
                    session.state.value,
                    session.fatigue_warning_level.value,
                ),
            )
        return session

    def get(self, session_id: str) -> ReviewSession | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def add_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO session_events(
                    session_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    json.dumps(payload) if payload is not None else None,
                    _dt(datetime.now(UTC)),
                ),
            )

    @staticmethod
    def _from_row(row: Any) -> ReviewSession:
        return ReviewSession(
            id=row["id"],
            operation_id=row["operation_id"],
            video_id=row["video_id"],
            operator_name=row["operator_name"],
            started_at=_parse_dt(row["started_at"]),
            ended_at=_parse_dt(row["ended_at"]) if row["ended_at"] else None,
            active_duration_s=float(row["active_duration_s"]),
            pause_duration_s=float(row["pause_duration_s"]),
            state=SessionState(row["state"]),
            fatigue_warning_level=FatigueWarningLevel(row["fatigue_warning_level"]),
        )


class SegmentRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, segment: ReviewSegment) -> ReviewSegment:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO review_segments(
                    id, video_id, start_timestamp_s, end_timestamp_s,
                    start_frame, end_frame, grid_cell, review_status,
                    quality_issues_json, operator_id, reviewed_at, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.id,
                    segment.video_id,
                    segment.start_timestamp_s,
                    segment.end_timestamp_s,
                    segment.start_frame,
                    segment.end_frame,
                    segment.grid_cell,
                    segment.review_status.value,
                    json.dumps([q.value for q in segment.quality_issues]),
                    segment.operator_id,
                    _dt(segment.reviewed_at),
                    segment.comment,
                ),
            )
        return segment

    def list_for_video(self, video_id: str) -> list[ReviewSegment]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM review_segments WHERE video_id = ? ORDER BY start_frame",
                (video_id,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: Any) -> ReviewSegment:
        issues = [QualityIssue(x) for x in json.loads(row["quality_issues_json"])]
        return ReviewSegment(
            id=row["id"],
            video_id=row["video_id"],
            start_timestamp_s=float(row["start_timestamp_s"]),
            end_timestamp_s=float(row["end_timestamp_s"]),
            start_frame=int(row["start_frame"]),
            end_frame=int(row["end_frame"]),
            grid_cell=row["grid_cell"],
            review_status=ReviewStatus(row["review_status"]),
            quality_issues=issues,
            operator_id=row["operator_id"],
            reviewed_at=_parse_dt(row["reviewed_at"]),
            comment=row["comment"],
        )


class CandidateRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, candidate: Candidate) -> Candidate:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO candidates(
                    id, operation_id, video_id, frame_index, timestamp_s,
                    drone_latitude, drone_longitude,
                    estimated_target_geometry_json, uncertainty_radius_m,
                    bounding_box_json, screenshot_path, crop_path,
                    category, evidence_tags_json, description, confidence,
                    review_status, requires_reflight, reflight_reason,
                    created_at, updated_at, relative_altitude, absolute_altitude,
                    gimbal_yaw, gimbal_pitch, gimbal_roll, focal_length, digital_zoom
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    candidate.id,
                    candidate.operation_id,
                    candidate.video_id,
                    candidate.frame_index,
                    candidate.timestamp_s,
                    candidate.drone_latitude,
                    candidate.drone_longitude,
                    json.dumps(candidate.estimated_target_geometry)
                    if candidate.estimated_target_geometry
                    else None,
                    candidate.uncertainty_radius_m,
                    json.dumps(candidate.bounding_box.model_dump())
                    if candidate.bounding_box
                    else None,
                    candidate.screenshot_path,
                    candidate.crop_path,
                    candidate.category.value,
                    json.dumps([t.value for t in candidate.evidence_tags]),
                    candidate.description,
                    candidate.confidence,
                    candidate.review_status.value,
                    int(candidate.requires_reflight),
                    candidate.reflight_reason,
                    _dt(candidate.created_at),
                    _dt(candidate.updated_at),
                    candidate.relative_altitude,
                    candidate.absolute_altitude,
                    candidate.gimbal_yaw,
                    candidate.gimbal_pitch,
                    candidate.gimbal_roll,
                    candidate.focal_length,
                    candidate.digital_zoom,
                ),
            )
            conn.execute(
                """
                INSERT INTO candidate_status_history(
                    candidate_id, old_status, new_status, changed_at, note
                ) VALUES (?, NULL, ?, ?, ?)
                """,
                (
                    candidate.id,
                    candidate.review_status.value,
                    _dt(candidate.created_at),
                    "created",
                ),
            )
        return candidate

    def update_status(
        self,
        candidate_id: str,
        new_status: ReviewStatus,
        note: str | None = None,
        *,
        requires_reflight: bool | None = None,
        reflight_reason: str | None = None,
    ) -> Candidate:
        now = datetime.now(UTC)
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"candidate not found: {candidate_id}")
            old_status = row["review_status"]
            if requires_reflight is None:
                requires_reflight = bool(row["requires_reflight"])
            if reflight_reason is None:
                reflight_reason = row["reflight_reason"]
            conn.execute(
                """
                UPDATE candidates
                SET review_status = ?, updated_at = ?,
                    requires_reflight = ?, reflight_reason = ?
                WHERE id = ?
                """,
                (
                    new_status.value,
                    _dt(now),
                    int(requires_reflight),
                    reflight_reason,
                    candidate_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO candidate_status_history(
                    candidate_id, old_status, new_status, changed_at, note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (candidate_id, old_status, new_status.value, _dt(now), note),
            )
            updated = conn.execute(
                "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        assert updated is not None
        return self._from_row(updated)

    def list_for_operation(self, operation_id: str) -> list[Candidate]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT * FROM candidates
                WHERE operation_id = ?
                ORDER BY created_at DESC
                """,
                (operation_id,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def count_for_operation(self, operation_id: str) -> int:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM candidates WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    @staticmethod
    def _from_row(row: Any) -> Candidate:
        bbox_raw = row["bounding_box_json"]
        bbox = BoundingBox(**json.loads(bbox_raw)) if bbox_raw else None
        geom_raw = row["estimated_target_geometry_json"]
        return Candidate(
            id=row["id"],
            operation_id=row["operation_id"],
            video_id=row["video_id"],
            frame_index=int(row["frame_index"]),
            timestamp_s=float(row["timestamp_s"]),
            drone_latitude=row["drone_latitude"],
            drone_longitude=row["drone_longitude"],
            estimated_target_geometry=json.loads(geom_raw) if geom_raw else None,
            uncertainty_radius_m=row["uncertainty_radius_m"],
            bounding_box=bbox,
            screenshot_path=row["screenshot_path"],
            crop_path=row["crop_path"],
            category=CandidateCategory(row["category"]),
            evidence_tags=[EvidenceTag(t) for t in json.loads(row["evidence_tags_json"])],
            description=row["description"],
            confidence=int(row["confidence"]),
            review_status=ReviewStatus(row["review_status"]),
            requires_reflight=bool(row["requires_reflight"]),
            reflight_reason=row["reflight_reason"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            relative_altitude=row["relative_altitude"],
            absolute_altitude=row["absolute_altitude"],
            gimbal_yaw=row["gimbal_yaw"],
            gimbal_pitch=row["gimbal_pitch"],
            gimbal_roll=row["gimbal_roll"],
            focal_length=row["focal_length"],
            digital_zoom=row["digital_zoom"],
        )
