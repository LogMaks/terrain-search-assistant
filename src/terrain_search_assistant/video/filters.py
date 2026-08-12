"""Non-destructive visual filters. Always operate on a copy."""

from __future__ import annotations

from enum import StrEnum
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray


class FilterName(StrEnum):
    ORIGINAL = "original"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    GAMMA = "gamma"
    SATURATION = "saturation"
    GRAYSCALE = "grayscale"
    CLAHE = "clahe"
    SHADOW_ENHANCEMENT = "shadow_enhancement"
    HIGHLIGHT_CLIPPING_MASK = "highlight_clipping_mask"


FILTER_WARNING = (
    "Коррекция изображения не восстанавливает детали,\n"
    "утраченные из-за пересвета или смаза."
)


def _ensure_uint8_bgr(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    if frame.dtype != np.uint8:
        raise TypeError(f"expected uint8 frame, got {frame.dtype}")
    if frame.ndim == 2:
        return cast(NDArray[np.uint8], cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    if frame.ndim == 3 and frame.shape[2] == 3:
        return frame
    raise ValueError(f"unsupported frame shape: {frame.shape}")


def apply_filter(
    frame: NDArray[np.uint8],
    name: FilterName,
    *,
    brightness: float = 0.0,
    contrast: float = 1.0,
    gamma: float = 1.0,
    saturation: float = 1.0,
    highlight_threshold: int = 245,
) -> NDArray[np.uint8]:
    """Apply a named filter to a copy of the frame. Original array is untouched."""
    if not (-100.0 <= brightness <= 100.0):
        raise ValueError("brightness must be in [-100, 100]")
    if not (0.1 <= contrast <= 3.0):
        raise ValueError("contrast must be in [0.1, 3.0]")
    if not (0.1 <= gamma <= 3.0):
        raise ValueError("gamma must be in [0.1, 3.0]")
    if not (0.0 <= saturation <= 3.0):
        raise ValueError("saturation must be in [0.0, 3.0]")
    if not (0 <= highlight_threshold <= 255):
        raise ValueError("highlight_threshold must be in [0, 255]")

    source = _ensure_uint8_bgr(frame)
    # Explicit copy so callers can verify identity separation.
    working = source.copy()

    if name == FilterName.ORIGINAL:
        return working

    if name == FilterName.BRIGHTNESS:
        return cast(NDArray[np.uint8], cv2.convertScaleAbs(working, alpha=1.0, beta=brightness))

    if name == FilterName.CONTRAST:
        return cast(NDArray[np.uint8], cv2.convertScaleAbs(working, alpha=contrast, beta=0))

    if name == FilterName.GAMMA:
        inv = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv) * 255 for i in range(256)]).astype("uint8")
        return cast(NDArray[np.uint8], cv2.LUT(working, table))

    if name == FilterName.SATURATION:
        hsv = cv2.cvtColor(working, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
        return cast(NDArray[np.uint8], cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR))

    if name == FilterName.GRAYSCALE:
        gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
        return cast(NDArray[np.uint8], cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))

    if name == FilterName.CLAHE:
        lab = cv2.cvtColor(working, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        merged = cv2.merge([l_ch, a_ch, b_ch])
        return cast(NDArray[np.uint8], cv2.cvtColor(merged, cv2.COLOR_LAB2BGR))

    if name == FilterName.SHADOW_ENHANCEMENT:
        lab = cv2.cvtColor(working, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        # Lift shadows via gamma on L channel only.
        inv = 1.0 / 0.7
        table = np.array([((i / 255.0) ** inv) * 255 for i in range(256)]).astype("uint8")
        l_ch = cv2.LUT(l_ch, table)
        merged = cv2.merge([l_ch, a_ch, b_ch])
        return cast(NDArray[np.uint8], cv2.cvtColor(merged, cv2.COLOR_LAB2BGR))

    if name == FilterName.HIGHLIGHT_CLIPPING_MASK:
        gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
        mask = gray >= highlight_threshold
        out = working.copy()
        out[mask] = (0, 0, 255)
        return out

    raise ValueError(f"unknown filter: {name}")
