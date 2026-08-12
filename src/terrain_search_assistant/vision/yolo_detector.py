"""YOLO detector adapter (optional ultralytics dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from terrain_search_assistant.vision.base import Detection


class YoloUnavailableError(RuntimeError):
    """Raised when ultralytics is not installed or weights are missing."""


class YoloDetector:
    """Ultralytics YOLO adapter.

    Empty detections mean 'model returned nothing', NOT 'area is clear'.
    Runs locally; does not upload frames.
    """

    name: str = "yolo"

    def __init__(
        self,
        weights_path: Path,
        *,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        device: str = "cpu",
        imgsz: int = 640,
        class_names: set[str] | None = None,
    ) -> None:
        if not 0.0 < conf_threshold <= 1.0:
            raise ValueError("conf_threshold must be in (0, 1]")
        weights_path = Path(weights_path)
        if not weights_path.is_file():
            raise YoloUnavailableError(
                f"Файл весов не найден: {weights_path}. "
                "Положите .pt локально (например models/yolov8n.pt) "
                "или скачайте вручную — приложение само веса не тянет без явного согласия."
            )
        try:
            from ultralytics import YOLO as _YOLO  # type: ignore[attr-defined]
        except ImportError as exc:
            raise YoloUnavailableError(
                "Пакет ultralytics не установлен. "
                "Установите: uv sync --extra yolo"
            ) from exc

        self.weights_path = weights_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.imgsz = imgsz
        self.class_names = class_names
        self._model: Any = _YOLO(str(weights_path))

    def detect(self, frame_bgr: NDArray[np.uint8]) -> list[Detection]:
        if frame_bgr.size == 0:
            raise ValueError("empty frame")
        results: Any = self._model.predict(
            source=frame_bgr,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )
        detections: list[Detection] = []
        if not results:
            return detections
        result: Any = results[0]
        names = result.names if isinstance(getattr(result, "names", None), dict) else {}
        boxes: Any = getattr(result, "boxes", None)
        if boxes is None:
            return detections
        xyxy_t = getattr(boxes, "xyxy", None)
        conf_t = getattr(boxes, "conf", None)
        cls_t = getattr(boxes, "cls", None)
        if xyxy_t is None:
            return detections
        xyxy = xyxy_t.cpu().numpy() if hasattr(xyxy_t, "cpu") else np.asarray(xyxy_t)
        if conf_t is None:
            confs = np.empty((0,))
        elif hasattr(conf_t, "cpu"):
            confs = conf_t.cpu().numpy()
        else:
            confs = np.asarray(conf_t)
        if cls_t is None:
            clss = np.empty((0,))
        elif hasattr(cls_t, "cpu"):
            clss = cls_t.cpu().numpy()
        else:
            clss = np.asarray(cls_t)
        for i in range(len(xyxy)):
            cls_id = int(clss[i]) if i < len(clss) else -1
            label = str(names.get(cls_id, f"class_{cls_id}"))
            if self.class_names is not None and label not in self.class_names:
                continue
            x1, y1, x2, y2 = [int(round(float(v))) for v in xyxy[i][:4]]
            width = max(1, x2 - x1)
            height = max(1, y2 - y1)
            detections.append(
                Detection(
                    label=label,
                    confidence=float(confs[i]) if i < len(confs) else 0.0,
                    x=max(0, x1),
                    y=max(0, y1),
                    width=width,
                    height=height,
                )
            )
        return detections
