"""Non-destructive filter tests."""

from __future__ import annotations

import numpy as np
import pytest

from terrain_search_assistant.video.filters import FilterName, apply_filter


def test_original_not_mutated() -> None:
    frame = np.random.randint(0, 255, (40, 50, 3), dtype=np.uint8)
    original = frame.copy()
    out = apply_filter(frame, FilterName.BRIGHTNESS, brightness=30)
    assert np.array_equal(frame, original)
    assert out is not frame
    assert out.shape == frame.shape
    assert out.dtype == np.uint8


@pytest.mark.parametrize(
    "name",
    [
        FilterName.ORIGINAL,
        FilterName.BRIGHTNESS,
        FilterName.CONTRAST,
        FilterName.GAMMA,
        FilterName.SATURATION,
        FilterName.GRAYSCALE,
        FilterName.CLAHE,
        FilterName.SHADOW_ENHANCEMENT,
        FilterName.HIGHLIGHT_CLIPPING_MASK,
    ],
)
def test_filters_preserve_shape(name: FilterName) -> None:
    frame = np.random.randint(0, 255, (32, 48, 3), dtype=np.uint8)
    out = apply_filter(frame, name)
    assert out.shape == frame.shape
    assert out.dtype == np.uint8


def test_grayscale_input_promoted() -> None:
    gray = np.random.randint(0, 255, (20, 30), dtype=np.uint8)
    out = apply_filter(gray, FilterName.CLAHE)
    assert out.ndim == 3
    assert out.shape[2] == 3


def test_param_ranges() -> None:
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        apply_filter(frame, FilterName.BRIGHTNESS, brightness=200)
    with pytest.raises(ValueError):
        apply_filter(frame, FilterName.GAMMA, gamma=0.0)
