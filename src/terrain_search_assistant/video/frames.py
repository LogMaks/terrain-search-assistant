"""Frame extraction via OpenCV. Inspection mode is frame-accurate only."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray


class FrameAccessError(RuntimeError):
    """Raised when a frame cannot be read."""


class FrameReader:
    """Sequential/random frame access for inspection mode."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"video file not found or moved: {self.path}")
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise FrameAccessError(f"cannot open video: {self.path}")

    @property
    def frame_count(self) -> int:
        value = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return max(value, 0)

    @property
    def fps(self) -> float:
        value = float(self._cap.get(cv2.CAP_PROP_FPS))
        return value if value > 0 else 25.0

    def read_frame(self, index: int) -> NDArray[np.uint8]:
        if index < 0 or (self.frame_count and index >= self.frame_count):
            raise FrameAccessError(f"frame index out of range: {index}")
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, float(index))
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise FrameAccessError(f"failed to read frame {index} from {self.path}")
        return np.asarray(frame, dtype=np.uint8)

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> FrameReader:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def frame_timecode(frame_index: int, fps: float) -> str:
    """Format HH:MM:SS.mmm for a frame index."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    total_ms = int(round(frame_index / fps * 1000.0))
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def split_grid(
    frame: NDArray[np.uint8],
    rows: int,
    cols: int,
) -> list[tuple[str, NDArray[np.uint8], tuple[int, int, int, int]]]:
    """Split frame into labeled cells. Returns (label, crop, x,y,w,h)."""
    if rows not in (2, 3) or cols not in (2, 3):
        raise ValueError("supported grids are 2x3 and 3x3")
    height, width = frame.shape[:2]
    cells: list[tuple[str, NDArray[np.uint8], tuple[int, int, int, int]]] = []
    for r in range(rows):
        for c in range(cols):
            y0 = r * height // rows
            y1 = (r + 1) * height // rows
            x0 = c * width // cols
            x1 = (c + 1) * width // cols
            label = f"R{r + 1}C{c + 1}"
            crop = frame[y0:y1, x0:x1].copy()
            cells.append((label, crop, (x0, y0, x1 - x0, y1 - y0)))
    return cells


def draw_grid_overlay(frame: NDArray[np.uint8], rows: int, cols: int) -> NDArray[np.uint8]:
    """Return a copy with grid lines drawn."""
    out = frame.copy()
    height, width = out.shape[:2]
    color = (0, 255, 255)
    for r in range(1, rows):
        y = r * height // rows
        cv2.line(out, (0, y), (width - 1, y), color, 1)
    for c in range(1, cols):
        x = c * width // cols
        cv2.line(out, (x, 0), (x, height - 1), color, 1)
    return out
