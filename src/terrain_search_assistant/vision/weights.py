"""Ensure local YOLO weights exist for operator use."""

from __future__ import annotations

import shutil
from pathlib import Path


def ultralytics_installed() -> bool:
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return False
    return True


def ensure_yolo_weights(target: Path, *, allow_download: bool = True) -> Path:
    """Return a usable weights path. Optionally download yolov8n.pt once."""
    target = Path(target)
    if target.is_file():
        return target

    if not allow_download:
        raise FileNotFoundError(f"YOLO weights not found: {target}")

    if not ultralytics_installed():
        raise ImportError(
            "ultralytics не установлен. Выполните: uv sync --extra yolo"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO as _YOLO  # type: ignore[attr-defined]

    # Triggers local cache download of yolov8n.pt on first use.
    model = _YOLO("yolov8n.pt")
    cached = Path(str(getattr(model, "ckpt_path", "") or ""))
    if cached.is_file():
        if cached.resolve() != target.resolve():
            shutil.copy2(cached, target)
        return target if target.is_file() else cached

    # Some ultralytics versions keep path on model.model
    alt = Path("yolov8n.pt")
    if alt.is_file():
        shutil.copy2(alt, target)
        return target

    raise FileNotFoundError(
        f"Не удалось сохранить веса в {target}. "
        "Скачайте yolov8n.pt вручную в каталог models/."
    )
