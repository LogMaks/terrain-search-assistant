"""Detector extension point. No ML in this iteration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Detection:
    """A detector finding. Empty list means 'no detections returned', not 'safe'."""

    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


class Detector(Protocol):
    """Adapter interface for future ML detectors."""

    name: str

    def detect(self, frame_bgr: NDArray[np.uint8]) -> list[Detection]:
        """Run detection on a BGR frame. Must not invent certainty about absence."""
        ...
