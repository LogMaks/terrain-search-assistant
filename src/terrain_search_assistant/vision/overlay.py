"""Draw detector overlays without mutating the source frame."""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from terrain_search_assistant.vision.base import Detection


def draw_detections(
    frame_bgr: NDArray[np.uint8],
    detections: list[Detection],
) -> NDArray[np.uint8]:
    """Return a copy with bounding boxes and labels."""
    out = frame_bgr.copy()
    for det in detections:
        x2 = det.x + det.width
        y2 = det.y + det.height
        cv2.rectangle(out, (det.x, det.y), (x2, y2), (0, 255, 0), 2)
        caption = f"{det.label} {det.confidence:.2f}"
        cv2.putText(
            out,
            caption,
            (det.x, max(16, det.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return out
