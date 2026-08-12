"""Inspection-mode review UI (frame-accurate)."""

from __future__ import annotations

from pathlib import Path

import cv2
import streamlit as st

from terrain_search_assistant.config import AppConfig
from terrain_search_assistant.domain.enums import (
    CandidateCategory,
    EvidenceTag,
    FatigueWarningLevel,
    QualityIssue,
    ReviewStatus,
    SessionState,
)
from terrain_search_assistant.domain.models import (
    BoundingBox,
    SearchOperation,
    TelemetrySample,
    VideoAsset,
)
from terrain_search_assistant.review.evidence import build_candidate
from terrain_search_assistant.review.progress import (
    build_segment,
    cell_labels,
    summarize_cell_statuses,
)
from terrain_search_assistant.review.sessions import ReviewSessionController, create_session
from terrain_search_assistant.storage.repositories import (
    CandidateRepository,
    SegmentRepository,
    SessionRepository,
)
from terrain_search_assistant.telemetry.dji_srt import SrtParseError, parse_dji_srt_file
from terrain_search_assistant.video.filters import FILTER_WARNING, FilterName, apply_filter
from terrain_search_assistant.video.frames import (
    FrameAccessError,
    FrameReader,
    draw_grid_overlay,
    frame_timecode,
    split_grid,
)


def _fatigue_banner(level: FatigueWarningLevel) -> None:
    if level == FatigueWarningLevel.BREAK_RECOMMENDED:
        st.warning("Рекомендуется сделать перерыв (активное время ≥ 20 мин).")
    elif level == FatigueWarningLevel.STRONG_WARNING:
        st.warning("Усиленное предупреждение: активное время ≥ 30 мин.")
    elif level == FatigueWarningLevel.HIGH_RISK:
        st.error(
            "Высокий риск усталости (≥ 40 мин активного просмотра). "
            "Участки, отмеченные сейчас, получат метку FATIGUE_RISK и не считаются "
            "равными нормальной проверке без этой отметки."
        )


def render_review_view(
    operation: SearchOperation,
    video: VideoAsset,
    session_repo: SessionRepository,
    segment_repo: SegmentRepository,
    candidate_repo: CandidateRepository,
    config: AppConfig,
) -> tuple[list[TelemetrySample], TelemetrySample | None, int]:
    st.subheader("Инспекция")
    st.info(
        "Инспекционный режим — покадровый. Непрерывное воспроизведение ≤0.5× "
        "потребует отдельного компонента и пока не реализовано. "
        "Стандартный плеер ниже — только навигация и не засчитывается как подтверждённый просмотр."
    )

    # Navigation player (not counted as review)
    with st.expander("Навигационный режим (не подтверждённый просмотр)", expanded=False):
        if Path(video.path).is_file():
            st.video(video.path)
        else:
            st.error(f"Файл недоступен: {video.path}")

    operator = st.text_input("Оператор / псевдоним", value=st.session_state.get("operator_name", "operator"))
    st.session_state["operator_name"] = operator

    ctrl: ReviewSessionController | None = st.session_state.get("session_ctrl")
    if ctrl is None or ctrl.session.video_id != video.id:
        session = create_session(
            operation_id=operation.id,
            video_id=video.id,
            operator_name=operator,
        )
        ctrl = ReviewSessionController(session, config=config)
        st.session_state["session_ctrl"] = ctrl

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Старт сессии"):
        ctrl.start()
        session_repo.save(ctrl.session)
        session_repo.add_event(ctrl.session.id, "start")
    if c2.button("Пауза") and ctrl.session.state == SessionState.ACTIVE:
        ctrl.pause()
        session_repo.save(ctrl.session)
        session_repo.add_event(ctrl.session.id, "pause")
    if c3.button("Продолжить") and ctrl.session.state == SessionState.PAUSED:
        ctrl.resume()
        session_repo.save(ctrl.session)
        session_repo.add_event(ctrl.session.id, "resume")
    if c4.button("Завершить сессию"):
        ctrl.end()
        session_repo.save(ctrl.session)
        session_repo.add_event(ctrl.session.id, "end")

    ctrl.tick()
    active_s = ctrl.current_active_seconds()
    st.metric("Активное время (с)", f"{active_s:.0f}")
    st.caption(
        f"Паузы: {ctrl.session.pause_duration_s:.0f} с · состояние: {ctrl.session.state.value} · "
        f"усталость: {ctrl.session.fatigue_warning_level.value}"
    )
    _fatigue_banner(ctrl.session.fatigue_warning_level)
    if (
        ctrl.session.fatigue_warning_level == FatigueWarningLevel.HIGH_RISK
        and not st.session_state.get("fatigue_logged")
    ):
        session_repo.add_event(
            ctrl.session.id,
            "fatigue_high_risk",
            {"active_s": active_s},
        )
        st.session_state["fatigue_logged"] = True

    samples: list[TelemetrySample] = []
    if video.srt_path:
        try:
            samples = parse_dji_srt_file(Path(video.srt_path), max_bytes=config.max_srt_bytes)
        except (SrtParseError, FileNotFoundError) as exc:
            st.warning(f"SRT: {exc}")

    try:
        reader = FrameReader(Path(video.path))
    except (FileNotFoundError, FrameAccessError) as exc:
        st.error(str(exc))
        return samples, None, 0

    frame_count = max(reader.frame_count, 1)
    fps = video.fps or reader.fps
    max_idx = max(frame_count - 1, 0)

    if "frame_index" not in st.session_state:
        st.session_state["frame_index"] = 0
    frame_index = int(st.session_state["frame_index"])
    frame_index = max(0, min(frame_index, max_idx))

    nav1, nav2, nav3, nav4, nav5, nav6 = st.columns(6)
    step = st.number_input("Шаг кадров", min_value=1, max_value=300, value=1)
    deltas = [(-30, nav1), (-5, nav2), (-1, nav3), (1, nav4), (5, nav5), (30, nav6)]
    for delta, col in deltas:
        if col.button(f"{delta:+d}"):
            frame_index = max(0, min(frame_index + delta, max_idx))

    frame_index = st.slider("Кадр", 0, max_idx, frame_index)
    if st.button(f"Шаг ±{step}"):
        frame_index = max(0, min(frame_index + int(step), max_idx))
    st.session_state["frame_index"] = frame_index

    try:
        frame = reader.read_frame(frame_index)
    except FrameAccessError as exc:
        st.error(str(exc))
        reader.close()
        return samples, None, frame_index
    finally:
        reader.close()

    tc = frame_timecode(frame_index, fps)
    st.write(f"Frame **{frame_index}** · таймкод **{tc}** · FPS {fps:.3f}")

    filter_name = st.selectbox("Фильтр", [f.value for f in FilterName], index=0)
    brightness = st.slider("Brightness", -100.0, 100.0, 0.0)
    contrast = st.slider("Contrast", 0.1, 3.0, 1.0)
    gamma = st.slider("Gamma", 0.1, 3.0, 1.0)
    saturation = st.slider("Saturation", 0.0, 3.0, 1.0)
    if st.button("Сброс фильтров"):
        st.rerun()

    st.warning(FILTER_WARNING)
    filtered = apply_filter(
        frame,
        FilterName(filter_name),
        brightness=brightness,
        contrast=contrast,
        gamma=gamma,
        saturation=saturation,
    )
    show_original = st.checkbox("Сравнить с оригиналом", value=False)
    if show_original:
        c_a, c_b = st.columns(2)
        c_a.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), caption="Оригинал", use_container_width=True)
        c_b.image(cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB), caption="Фильтр", use_container_width=True)
    else:
        st.image(cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB), use_container_width=True)

    grid_mode = st.radio("Сетка", ["нет", "2×3", "3×3"], horizontal=True)
    rows, cols = (0, 0)
    if grid_mode == "2×3":
        rows, cols = 2, 3
    elif grid_mode == "3×3":
        rows, cols = 3, 3

    segments = segment_repo.list_for_video(video.id)
    cell_status = summarize_cell_statuses(segments, frame_index)

    if rows and cols:
        overlay = draw_grid_overlay(filtered, rows, cols)
        st.image(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB), caption="Сетка", use_container_width=True)
        cells = split_grid(filtered, rows, cols)
        focus = st.selectbox("Открыть ячейку крупно", ["—"] + [c[0] for c in cells])
        if focus != "—":
            for label, crop, _box in cells:
                if label == focus:
                    st.image(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), caption=label, use_container_width=True)
                    break

        st.markdown("#### Статусы ячеек")
        for label in cell_labels(rows, cols):
            st.caption(f"{label}: {cell_status.get(label, ReviewStatus.NOT_REVIEWED).value}")
            status = st.selectbox(
                f"Статус {label}",
                [s.value for s in ReviewStatus],
                key=f"cell_status_{frame_index}_{label}",
            )
            issues = st.multiselect(
                f"Качество {label}",
                [q.value for q in QualityIssue],
                key=f"cell_issues_{frame_index}_{label}",
            )
            if st.button(f"Сохранить {label}", key=f"save_cell_{frame_index}_{label}"):
                if ctrl.session.state != SessionState.ACTIVE:
                    st.error("Начните активную сессию инспекции")
                else:
                    seg = build_segment(
                        video_id=video.id,
                        frame_index=frame_index,
                        fps=fps,
                        grid_cell=label,
                        review_status=ReviewStatus(status),
                        quality_issues=[QualityIssue(i) for i in issues],
                        operator_id=ctrl.session.id,
                        fatigue_level=ctrl.session.fatigue_warning_level,
                    )
                    segment_repo.create(seg)
                    session_repo.save(ctrl.session)
                    st.success(f"Сохранено: {label}")
                    st.rerun()

    st.markdown("#### Отметка качества текущего кадра")
    frame_status = st.selectbox("Статус кадра", [s.value for s in ReviewStatus], key="frame_status")
    frame_issues = st.multiselect("Проблемы качества", [q.value for q in QualityIssue], key="frame_issues")
    frame_comment = st.text_input("Комментарий к кадру", key="frame_comment")
    if st.button("Сохранить статус кадра"):
        if ctrl.session.state != SessionState.ACTIVE:
            st.error("Начните активную сессию инспекции")
        else:
            seg = build_segment(
                video_id=video.id,
                frame_index=frame_index,
                fps=fps,
                grid_cell=None,
                review_status=ReviewStatus(frame_status),
                quality_issues=[QualityIssue(i) for i in frame_issues],
                operator_id=ctrl.session.id,
                comment=frame_comment or None,
                fatigue_level=ctrl.session.fatigue_warning_level,
            )
            segment_repo.create(seg)
            session_repo.save(ctrl.session)
            st.success("Статус кадра сохранён")

    st.markdown("#### Кандидат")
    st.caption("Координаты дрона из телеметрии")
    category = st.selectbox("Категория", [c.value for c in CandidateCategory])
    tags = st.multiselect("Evidence tags", [t.value for t in EvidenceTag])
    description = st.text_area("Описание")
    confidence = st.slider("Confidence", 1, 5, 3)
    requires_reflight = st.checkbox("Requires reflight", value=False)
    reflight_reason = st.text_input("Причина повторного облёта") if requires_reflight else None
    use_bbox = st.checkbox("Задать crop bbox (пиксели)", value=False)
    bbox: BoundingBox | None = None
    if use_bbox:
        bx = st.number_input("x", min_value=0, value=0)
        by = st.number_input("y", min_value=0, value=0)
        bw = st.number_input("width", min_value=1, value=100)
        bh = st.number_input("height", min_value=1, value=100)
        bbox = BoundingBox(x=int(bx), y=int(by), width=int(bw), height=int(bh))

    current_sample = samples[frame_index] if frame_index < len(samples) else (
        samples[-1] if samples else None
    )
    if st.button("Сохранить кандидата", type="primary"):
        try:
            cand = build_candidate(
                operation_id=operation.id,
                video_id=video.id,
                frame_index=frame_index,
                timestamp_s=frame_index / fps if fps else float(frame_index),
                frame_bgr=frame,
                artifacts_dir=config.artifacts_dir,
                category=CandidateCategory(category),
                evidence_tags=[EvidenceTag(t) for t in tags],
                description=description,
                confidence=int(confidence),
                requires_reflight=requires_reflight,
                reflight_reason=reflight_reason,
                bounding_box=bbox,
                telemetry=current_sample,
            )
            candidate_repo.create(cand)
            st.success(f"Кандидат сохранён: {cand.id}")
        except (ValueError, OSError) as exc:
            st.error(str(exc))

    return samples, current_sample, frame_index
