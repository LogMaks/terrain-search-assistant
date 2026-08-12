"""Application configuration. Thresholds are overridable without code changes."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class FatigueThresholds(BaseModel):
    """Active review duration thresholds (seconds)."""

    break_recommendation_s: int = Field(default=20 * 60, ge=1)
    strong_warning_s: int = Field(default=30 * 60, ge=1)
    high_risk_s: int = Field(default=40 * 60, ge=1)


class AppConfig(BaseModel):
    """Runtime configuration for a local deployment."""

    data_dir: Path = Field(default=Path("data"))
    artifacts_dir: Path = Field(default=Path("data/artifacts"))
    db_path: Path = Field(default=Path("data/terrain_search.db"))
    max_srt_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    default_visir_length_m: float = Field(default=1000.0, gt=0.0)
    overlap_warning_ratio: float = Field(default=0.1, ge=0.0, le=1.0)
    fatigue: FatigueThresholds = Field(default_factory=FatigueThresholds)

    def ensure_dirs(self) -> None:
        """Create local data directories if missing."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "crops").mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = AppConfig()
