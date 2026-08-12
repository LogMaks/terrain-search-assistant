"""Tests for SRT track helpers."""

from __future__ import annotations

from pathlib import Path

from terrain_search_assistant.domain.enums import IndexingStatus
from terrain_search_assistant.domain.models import TelemetrySample, VideoAsset
from terrain_search_assistant.telemetry.track import (
    gps_track_points,
    list_srt_files,
    load_bound_telemetry,
    track_summary,
)


def test_list_srt_files(tmp_path: Path) -> None:
    (tmp_path / "a.SRT").write_text("x")
    (tmp_path / "b.srt").write_text("y")
    (tmp_path / "c.mp4").write_bytes(b"\x00")
    found = list_srt_files(tmp_path)
    assert [p.name.lower() for p in found] == ["a.srt", "b.srt"]


def test_track_summary_from_samples() -> None:
    samples = [
        TelemetrySample(
            start_time="00:00:00,000",
            end_time="00:00:00,033",
            latitude=46.0,
            longitude=9.0,
        ),
        TelemetrySample(
            start_time="00:00:00,033",
            end_time="00:00:00,066",
            latitude=46.1,
            longitude=9.1,
        ),
    ]
    points = gps_track_points(samples)
    assert len(points) == 2
    summary = track_summary(samples)
    assert summary["has_track"] is True
    assert summary["gps_points"] == 2


def test_load_bound_telemetry(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample_dji.srt"
    video = VideoAsset(
        operation_id="op",
        path=str(tmp_path / "x.mp4"),
        filename="x.mp4",
        srt_path=str(fixture),
        indexing_status=IndexingStatus.INDEXED,
    )
    samples, err = load_bound_telemetry(video)
    assert err is None
    assert len(samples) >= 3
    assert track_summary(samples)["has_track"] is True
