"""SQLite connection, schema init, and transaction helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    comment TEXT
);

CREATE TABLE IF NOT EXISTS sectors (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(id),
    name TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    geometry_json TEXT NOT NULL,
    area_m2 REAL NOT NULL,
    comment TEXT,
    requires_reflight INTEGER NOT NULL DEFAULT 0,
    reflight_reason TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(id),
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    filesize INTEGER,
    duration_s REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    codec TEXT,
    srt_path TEXT,
    indexing_status TEXT NOT NULL,
    fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS review_sessions (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(id),
    video_id TEXT NOT NULL REFERENCES videos(id),
    operator_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    active_duration_s REAL NOT NULL DEFAULT 0,
    pause_duration_s REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    fatigue_warning_level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_segments (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(id),
    start_timestamp_s REAL NOT NULL,
    end_timestamp_s REAL NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    grid_cell TEXT,
    review_status TEXT NOT NULL,
    quality_issues_json TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    comment TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES operations(id),
    video_id TEXT NOT NULL REFERENCES videos(id),
    frame_index INTEGER NOT NULL,
    timestamp_s REAL NOT NULL,
    drone_latitude REAL,
    drone_longitude REAL,
    estimated_target_geometry_json TEXT,
    uncertainty_radius_m REAL,
    bounding_box_json TEXT,
    screenshot_path TEXT NOT NULL,
    crop_path TEXT,
    category TEXT NOT NULL,
    evidence_tags_json TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    review_status TEXT NOT NULL,
    requires_reflight INTEGER NOT NULL DEFAULT 0,
    reflight_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    relative_altitude REAL,
    absolute_altitude REAL,
    gimbal_yaw REAL,
    gimbal_pitch REAL,
    gimbal_roll REAL,
    focal_length REAL,
    digital_zoom REAL
);

CREATE TABLE IF NOT EXISTS candidate_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL REFERENCES candidates(id),
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES review_sessions(id),
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
"""


class Database:
    """Thin SQLite wrapper with FK enforcement and schema init."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at)"
                    " VALUES (?, datetime('now'))",
                    (SCHEMA_VERSION,),
                )
