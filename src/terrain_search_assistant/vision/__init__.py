"""Vision package: detector adapters."""

from terrain_search_assistant.vision.base import Detection, Detector
from terrain_search_assistant.vision.factory import create_detector
from terrain_search_assistant.vision.null_detector import NullDetector

__all__ = ["Detection", "Detector", "NullDetector", "create_detector"]
