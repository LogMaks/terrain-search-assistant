"""Review session fatigue timer tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from terrain_search_assistant.config import AppConfig, FatigueThresholds
from terrain_search_assistant.domain.enums import FatigueWarningLevel, SessionState
from terrain_search_assistant.review.sessions import (
    ReviewSessionController,
    create_session,
    fatigue_level_for_active_seconds,
)


def test_fatigue_thresholds() -> None:
    th = FatigueThresholds(
        break_recommendation_s=20 * 60,
        strong_warning_s=30 * 60,
        high_risk_s=40 * 60,
    )
    assert fatigue_level_for_active_seconds(0, th) == FatigueWarningLevel.NONE
    assert fatigue_level_for_active_seconds(20 * 60, th) == FatigueWarningLevel.BREAK_RECOMMENDED
    assert fatigue_level_for_active_seconds(30 * 60, th) == FatigueWarningLevel.STRONG_WARNING
    assert fatigue_level_for_active_seconds(40 * 60, th) == FatigueWarningLevel.HIGH_RISK


def test_session_active_vs_pause() -> None:
    t0 = datetime(2020, 1, 1, tzinfo=UTC)
    clock = {"now": t0}

    def now() -> datetime:
        return clock["now"]

    session = create_session(operation_id="op", video_id="vid", operator_name="op1")
    session.started_at = t0
    cfg = AppConfig(fatigue=FatigueThresholds())
    ctrl = ReviewSessionController(session, config=cfg, clock=now)
    ctrl.start()
    clock["now"] = t0 + timedelta(minutes=10)
    ctrl.pause()
    assert ctrl.session.active_duration_s == pytest.approx(600.0)
    clock["now"] = t0 + timedelta(minutes=25)
    ctrl.resume()
    clock["now"] = t0 + timedelta(minutes=45)
    ctrl.end()
    # 10 min active + 20 min active = 30 min; 15 min pause
    assert ctrl.session.active_duration_s == pytest.approx(1800.0)
    assert ctrl.session.pause_duration_s == pytest.approx(900.0)
    assert ctrl.session.state == SessionState.ENDED
    assert ctrl.session.fatigue_warning_level == FatigueWarningLevel.STRONG_WARNING


def test_high_risk_transition() -> None:
    t0 = datetime(2020, 1, 1, tzinfo=UTC)
    clock = {"now": t0}

    def now() -> datetime:
        return clock["now"]

    session = create_session(operation_id="op", video_id="vid", operator_name="op1")
    ctrl = ReviewSessionController(session, clock=now)
    ctrl.start()
    clock["now"] = t0 + timedelta(minutes=41)
    ctrl.tick()
    assert ctrl.session.fatigue_warning_level == FatigueWarningLevel.HIGH_RISK
