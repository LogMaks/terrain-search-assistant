"""Detector factory: null by default, YOLO when configured and available."""

from __future__ import annotations

from pathlib import Path

from terrain_search_assistant.vision.base import Detector
from terrain_search_assistant.vision.null_detector import NullDetector
from terrain_search_assistant.vision.yolo_detector import YoloDetector, YoloUnavailableError


def create_detector(
    kind: str,
    *,
    weights_path: Path | None = None,
    conf_threshold: float = 0.25,
    device: str = "cpu",
    person_only: bool = True,
) -> Detector:
    """Create a detector instance.

    kind:
      - "null": always empty results (default safe mode)
      - "yolo": local Ultralytics YOLO
    """
    normalized = kind.strip().lower()
    if normalized in {"null", "none", "off"}:
        return NullDetector()
    if normalized == "yolo":
        if weights_path is None:
            raise YoloUnavailableError("weights_path is required for YOLO")
        class_names = {"person"} if person_only else None
        return YoloDetector(
            weights_path,
            conf_threshold=conf_threshold,
            device=device,
            class_names=class_names,
        )
    raise ValueError(f"unknown detector kind: {kind}")
