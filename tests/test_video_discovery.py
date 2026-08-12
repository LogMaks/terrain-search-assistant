"""Video discovery tests (no real drone footage)."""

from __future__ import annotations

from pathlib import Path

from terrain_search_assistant.video.discovery import discover_videos


def test_discover_pairs_srt(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    srt = tmp_path / "clip.SRT"
    other = tmp_path / "notes.txt"
    video.write_bytes(b"\x00" * 2048)
    srt.write_text("dummy")
    other.write_text("x")

    found = discover_videos(tmp_path)
    assert len(found) == 1
    assert found[0].path.name == "clip.mp4"
    assert found[0].srt_path is not None
    assert found[0].srt_path.name == "clip.SRT"
    assert found[0].fingerprint


def test_discover_pairs_case_insensitive_stem(tmp_path: Path) -> None:
    video = tmp_path / "DJI_0001.MP4"
    srt = tmp_path / "dji_0001.srt"
    video.write_bytes(b"\x00" * 512)
    srt.write_text("dummy")
    found = discover_videos(tmp_path)
    assert found[0].srt_path is not None
    assert found[0].srt_path.name.lower() == "dji_0001.srt"


def test_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "x.mov").write_bytes(b"\x00" * 100)
    assert discover_videos(tmp_path, recursive=False) == []
    assert len(discover_videos(tmp_path, recursive=True)) == 1
