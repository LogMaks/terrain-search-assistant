"""Review session lifecycle and fatigue timer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from terrain_search_assistant.config import DEFAULT_CONFIG, AppConfig, FatigueThresholds
from terrain_search_assistant.domain.enums import FatigueWarningLevel, SessionState
from terrain_search_assistant.domain.models import ReviewSession


def utc_now() -> datetime:
    return datetime.now(UTC)


def fatigue_level_for_active_seconds(
    active_duration_s: float,
    thresholds: FatigueThresholds | None = None,
) -> FatigueWarningLevel:
    """Map active review time to fatigue warning level."""
    th = thresholds or DEFAULT_CONFIG.fatigue
    if active_duration_s >= th.high_risk_s:
        return FatigueWarningLevel.HIGH_RISK
    if active_duration_s >= th.strong_warning_s:
        return FatigueWarningLevel.STRONG_WARNING
    if active_duration_s >= th.break_recommendation_s:
        return FatigueWarningLevel.BREAK_RECOMMENDED
    return FatigueWarningLevel.NONE


class ReviewSessionController:
    """In-memory session state machine. Persist via SessionRepository separately."""

    def __init__(
        self,
        session: ReviewSession,
        *,
        config: AppConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.config = config or DEFAULT_CONFIG
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._segment_started_at: datetime | None = (
            session.started_at if session.state == SessionState.ACTIVE else None
        )
        self._pause_started_at: datetime | None = None

    def start(self) -> ReviewSession:
        if self.session.state not in {SessionState.IDLE, SessionState.PAUSED}:
            raise ValueError(f"cannot start from state {self.session.state}")
        now = self._clock()
        if self.session.state == SessionState.IDLE:
            self.session.started_at = now
            self.session.active_duration_s = 0.0
            self.session.pause_duration_s = 0.0
        elif self.session.state == SessionState.PAUSED and self._pause_started_at is not None:
            self.session.pause_duration_s += (now - self._pause_started_at).total_seconds()
            self._pause_started_at = None
        self.session.state = SessionState.ACTIVE
        self._segment_started_at = now
        self._refresh_fatigue()
        return self.session

    def pause(self) -> ReviewSession:
        if self.session.state != SessionState.ACTIVE:
            raise ValueError("can only pause an active session")
        now = self._clock()
        self._accumulate_active(now)
        self.session.state = SessionState.PAUSED
        self._pause_started_at = now
        self._refresh_fatigue()
        return self.session

    def resume(self) -> ReviewSession:
        return self.start()

    def tick(self) -> ReviewSession:
        """Refresh durations and fatigue without changing state."""
        now = self._clock()
        if self.session.state == SessionState.ACTIVE and self._segment_started_at is not None:
            provisional = self.session.active_duration_s + (
                now - self._segment_started_at
            ).total_seconds()
            self.session.fatigue_warning_level = fatigue_level_for_active_seconds(
                provisional, self.config.fatigue
            )
        else:
            self._refresh_fatigue()
        return self.session

    def end(self) -> ReviewSession:
        if self.session.state == SessionState.ENDED:
            return self.session
        now = self._clock()
        if self.session.state == SessionState.ACTIVE:
            self._accumulate_active(now)
        elif self.session.state == SessionState.PAUSED and self._pause_started_at is not None:
            self.session.pause_duration_s += (now - self._pause_started_at).total_seconds()
            self._pause_started_at = None
        self.session.state = SessionState.ENDED
        self.session.ended_at = now
        self._refresh_fatigue()
        return self.session

    def current_active_seconds(self) -> float:
        now = self._clock()
        if self.session.state == SessionState.ACTIVE and self._segment_started_at is not None:
            return self.session.active_duration_s + (
                now - self._segment_started_at
            ).total_seconds()
        return self.session.active_duration_s

    def _accumulate_active(self, now: datetime) -> None:
        if self._segment_started_at is None:
            return
        self.session.active_duration_s += (now - self._segment_started_at).total_seconds()
        self._segment_started_at = None

    def _refresh_fatigue(self) -> None:
        self.session.fatigue_warning_level = fatigue_level_for_active_seconds(
            self.session.active_duration_s, self.config.fatigue
        )


def create_session(
    *,
    operation_id: str,
    video_id: str,
    operator_name: str,
) -> ReviewSession:
    now = datetime.now(UTC)
    return ReviewSession(
        operation_id=operation_id,
        video_id=video_id,
        operator_name=operator_name,
        started_at=now,
        state=SessionState.IDLE,
        fatigue_warning_level=FatigueWarningLevel.NONE,
    )
