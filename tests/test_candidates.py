"""Candidate evidence and repository persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from terrain_search_assistant.domain.enums import (
    CandidateCategory,
    EvidenceTag,
    OperationStatus,
    ReviewStatus,
)
from terrain_search_assistant.domain.models import BoundingBox, SearchOperation, VideoAsset
from terrain_search_assistant.review.evidence import build_candidate
from terrain_search_assistant.storage.database import Database
from terrain_search_assistant.storage.repositories import (
    CandidateRepository,
    OperationRepository,
    VideoRepository,
)


def test_build_candidate_requires_tags(tmp_path: Path) -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="evidence"):
        build_candidate(
            operation_id="op",
            video_id="vid",
            frame_index=0,
            timestamp_s=0.0,
            frame_bgr=frame,
            artifacts_dir=tmp_path,
            category=CandidateCategory.DARK_SPOT,
            evidence_tags=[],
            description="x",
            confidence=2,
            requires_reflight=False,
            reflight_reason=None,
        )


def test_candidate_persist_and_status_history(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.db")
    op_repo = OperationRepository(db)
    video_repo = VideoRepository(db)
    cand_repo = CandidateRepository(db)

    now = datetime.now(UTC)
    op = SearchOperation(
        name="test",
        created_at=now,
        updated_at=now,
        status=OperationStatus.ACTIVE,
    )
    op_repo.create(op)
    video = VideoAsset(
        operation_id=op.id,
        path="/tmp/fake.mp4",
        filename="fake.mp4",
    )
    video_repo.upsert(video)

    frame = np.full((80, 120, 3), 40, dtype=np.uint8)
    cand = build_candidate(
        operation_id=op.id,
        video_id=video.id,
        frame_index=3,
        timestamp_s=1.5,
        frame_bgr=frame,
        artifacts_dir=tmp_path / "artifacts",
        category=CandidateCategory.PERSON_LIKE,
        evidence_tags=[EvidenceTag.GEOMETRY, EvidenceTag.DARK_ON_SNOW],
        description="dark figure on snow",
        confidence=4,
        requires_reflight=True,
        reflight_reason="need lower pass",
        bounding_box=BoundingBox(x=10, y=10, width=20, height=20),
    )
    cand_repo.create(cand)
    assert (tmp_path / "artifacts" / "screenshots").exists()
    assert cand.crop_path is not None

    updated = cand_repo.update_status(cand.id, ReviewStatus.REVIEWED_CLEAR, note="later reject")
    assert updated.review_status == ReviewStatus.REVIEWED_CLEAR
    listed = cand_repo.list_for_operation(op.id)
    assert len(listed) == 1
    assert listed[0].id == cand.id
