"""Tests for detector adapters without requiring ultralytics/weights."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from terrain_search_assistant.vision.base import Detection
from terrain_search_assistant.vision.factory import create_detector
from terrain_search_assistant.vision.null_detector import NullDetector
from terrain_search_assistant.vision.overlay import draw_detections
from terrain_search_assistant.vision.yolo_detector import YoloDetector, YoloUnavailableError


def test_null_detector_empty() -> None:
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    dets = NullDetector().detect(frame)
    assert dets == []


def test_factory_null() -> None:
    det = create_detector("null")
    assert det.name == "null"


def test_yolo_missing_weights(tmp_path: Path) -> None:
    with pytest.raises(YoloUnavailableError, match="не найден"):
        YoloDetector(tmp_path / "missing.pt")


def test_draw_detections_does_not_mutate() -> None:
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    original = frame.copy()
    dets = [Detection(label="person", confidence=0.9, x=5, y=5, width=10, height=10)]
    out = draw_detections(frame, dets)
    assert np.array_equal(frame, original)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)
