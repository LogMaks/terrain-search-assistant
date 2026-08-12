"""Null detector: architectural extension point only."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from terrain_search_assistant.vision.base import Detection, Detector


class NullDetector:
    """Detects nothing. Absence of results must not be interpreted as 'clear'."""

    name: str = "null"

    def detect(self, frame_bgr: NDArray[np.uint8]) -> list[Detection]:
        if frame_bgr.size == 0:
            raise ValueError("empty frame")
        return []


def as_detector(detector: NullDetector) -> Detector:
    return detector
