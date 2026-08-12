"""Inspection-mode review UI (frame-accurate), simplified layout."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from numpy.typing import NDArray

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
from terrain_search_assistant.vision.base import Detection
from terrain_search_assistant.vision.factory import create_detector
from terrain_search_assistant.vision.overlay import draw_detections
from terrain_search_assistant.vision.weights import ensure_yolo_weights, ultralytics_installed
from terrain_search_assistant.vision.yolo_detector import YoloUnavailableError


def _fatigue_banner(level: FatigueWarningLevel) -> None:
    if level == FatigueWarningLevel.BREAK_RECOMMENDED:
        st.warning("Перерыв рекомендован (≥ 20 мин).")
    elif level == FatigueWarningLevel.STRONG_WARNING:
        st.warning("Усиленное предупреждение (≥ 30 мин).")
    elif level == FatigueWarningLevel.HIGH_RISK:
        st.error("Высокий риск усталости (≥ 40 мин). Новые отметки получат FATIGUE_RISK.")


def _show_frame(frame_bgr: NDArray[np.uint8], *, caption: str | None = None) -> None:
    st.image(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB), caption=caption, width="stretch")


def _load_detections() -> list[Detection]:
    raw = st.session_state.get("yolo_detections", [])
    return [
        Detection(
            label=str(item["label"]),
            confidence=float(item["confidence"]),
            x=int(item["x"]),
            y=int(item["y"]),
            width=int(item["width"]),
            height=int(item["height"]),
        )
        for item in raw
    ]


def _ensure_session_ctrl(
    operation: SearchOperation,
    video: VideoAsset,
    config: AppConfig,
) -> ReviewSessionController:
    ctrl: ReviewSessionController | None = st.session_state.get("session_ctrl")
    operator = st.session_state.get("operator_name", "operator")
    if ctrl is None or ctrl.session.video_id != video.id:
        session = create_session(
            operation_id=operation.id,
            video_id=video.id,
            operator_name=str(operator),
        )
        ctrl = ReviewSessionController(session, config=config)
        st.session_state["session_ctrl"] = ctrl
    return ctrl


def render_review_view(
    operation: SearchOperation,
    video: VideoAsset,
    session_repo: SessionRepository,
    segment_repo: SegmentRepository,
    candidate_repo: CandidateRepository,
    config: AppConfig,
) -> tuple[list[TelemetrySample], TelemetrySample | None, int]:
    st.subheader("Инспекция")
    st.caption(
        f"{video.filename} · покадровый режим · навигационный плеер не считается просмотром"
    )

    ctrl = _ensure_session_ctrl(operation, video, config)

    with st.expander("Сессия оператора", expanded=False):
        operator = st.text_input(
            "Оператор",
            value=st.session_state.get("operator_name", "operator"),
        )
        st.session_state["operator_name"] = operator
        ctrl.session.operator_name = operator

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Старт"):
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
        if c4.button("Завершить"):
            ctrl.end()
            session_repo.save(ctrl.session)
            session_repo.add_event(ctrl.session.id, "end")

        ctrl.tick()
        active_s = ctrl.current_active_seconds()
        st.caption(
            f"Активно {active_s:.0f} с · паузы {ctrl.session.pause_duration_s:.0f} с · "
            f"{ctrl.session.state.value} · {ctrl.session.fatigue_warning_level.value}"
        )
        _fatigue_banner(ctrl.session.fatigue_warning_level)
        if (
            ctrl.session.fatigue_warning_level == FatigueWarningLevel.HIGH_RISK
            and not st.session_state.get("fatigue_logged")
        ):
            session_repo.add_event(ctrl.session.id, "fatigue_high_risk", {"active_s": active_s})
            st.session_state["fatigue_logged"] = True

    ctrl.tick()

    with st.expander("Навигационный плеер (не подтверждённый просмотр)", expanded=False):
        if Path(video.path).is_file():
            st.video(video.path)
        else:
            st.error(f"Файл недоступен: {video.path}")

    samples: list[TelemetrySample] = []
    if video.srt_path:
        try:
            samples = parse_dji_srt_file(Path(video.srt_path), max_bytes=config.max_srt_bytes)
            st.caption(f"SRT: {len(samples)} семплов")
        except (SrtParseError, FileNotFoundError) as exc:
            st.warning(f"SRT: {exc}")
    else:
        st.caption("Без SRT — трек недоступен, инспекция работает")

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
    frame_index = max(0, min(int(st.session_state["frame_index"]), max_idx))

    main_col, side_col = st.columns([3, 1], gap="medium")

    with side_col:
        st.markdown("**Кадр**")
        jump = st.number_input("№", min_value=0, max_value=max_idx, value=frame_index, step=1)
        if int(jump) != frame_index:
            frame_index = int(jump)
        n1, n2, n3 = st.columns(3)
        if n1.button("-30"):
            frame_index = max(0, frame_index - 30)
        if n2.button("-1"):
            frame_index = max(0, frame_index - 1)
        if n3.button("+1"):
            frame_index = min(max_idx, frame_index + 1)
        n4, n5, n6 = st.columns(3)
        if n4.button("+5"):
            frame_index = min(max_idx, frame_index + 5)
        if n5.button("+30"):
            frame_index = min(max_idx, frame_index + 30)
        step = st.number_input("Шаг", min_value=1, max_value=300, value=1)
        if st.button(f"±{int(step)}"):
            frame_index = max(0, min(frame_index + int(step), max_idx))
        frame_index = st.slider("Таймлайн", 0, max_idx, frame_index)
        st.session_state["frame_index"] = frame_index

        st.markdown("**Вид**")
        filter_name = st.selectbox("Фильтр", [f.value for f in FilterName], index=0)
        show_original = st.checkbox("Сравнить с оригиналом", value=False)
        brightness = 0.0
        contrast = 1.0
        gamma = 1.0
        saturation = 1.0
        if filter_name != FilterName.ORIGINAL.value:
            brightness = st.slider("Яркость", -100.0, 100.0, 0.0)
            contrast = st.slider("Контраст", 0.1, 3.0, 1.0)
            if filter_name == FilterName.GAMMA.value:
                gamma = st.slider("Gamma", 0.1, 3.0, 1.0)
            if filter_name == FilterName.SATURATION.value:
                saturation = st.slider("Насыщенность", 0.0, 3.0, 1.0)
            st.caption(FILTER_WARNING.replace("\n", " "))

        grid_mode = st.radio("Сетка", ["нет", "2×3", "3×3"], horizontal=True)
        show_yolo_boxes = st.checkbox(
            "Показать YOLO на кадре",
            value=bool(st.session_state.get("yolo_detections")),
        )

        st.markdown("**YOLO**")
        yolo_ready = ultralytics_installed() and Path(config.yolo_weights_path).is_file()
        st.caption("готов" if yolo_ready else "не установлен")
        conf = st.slider("conf", 0.05, 0.95, float(config.yolo_conf_threshold), key="yolo_conf")
        person_only = st.checkbox("только person", value=False, key="yolo_person")
        if st.button("Запустить YOLO", type="primary", key="yolo_run"):
            try:
                weights_path = ensure_yolo_weights(
                    Path(config.yolo_weights_path),
                    allow_download=not Path(config.yolo_weights_path).is_file(),
                )
                cache_key = f"{weights_path}|{conf}|{person_only}|{config.yolo_device}"
                detector = st.session_state.get("yolo_detector")
                if detector is None or st.session_state.get("yolo_detector_key") != cache_key:
                    detector = create_detector(
                        "yolo",
                        weights_path=weights_path,
                        conf_threshold=float(conf),
                        device=config.yolo_device,
                        person_only=person_only,
                    )
                    st.session_state["yolo_detector"] = detector
                    st.session_state["yolo_detector_key"] = cache_key
                st.session_state["yolo_run_pending"] = True
            except (YoloUnavailableError, ValueError, OSError, ImportError, FileNotFoundError) as exc:
                st.error(str(exc))
        if st.button("Очистить YOLO", key="yolo_clear"):
            st.session_state["yolo_detections"] = []
            st.session_state.pop("yolo_detector_key", None)

    try:
        frame = reader.read_frame(frame_index)
    except FrameAccessError as exc:
        st.error(str(exc))
        reader.close()
        return samples, None, frame_index
    finally:
        reader.close()

    filtered = apply_filter(
        frame,
        FilterName(filter_name),
        brightness=brightness,
        contrast=contrast,
        gamma=gamma,
        saturation=saturation,
    )

    if st.session_state.pop("yolo_run_pending", False):
        detector = st.session_state.get("yolo_detector")
        if detector is not None:
            try:
                detections_run = detector.detect(filtered)
                st.session_state["yolo_detections"] = [
                    {
                        "label": d.label,
                        "confidence": d.confidence,
                        "x": d.x,
                        "y": d.y,
                        "width": d.width,
                        "height": d.height,
                    }
                    for d in detections_run
                ]
            except (ValueError, OSError) as exc:
                st.error(str(exc))

    detections = _load_detections()
    display = filtered
    if show_yolo_boxes and detections:
        display = draw_detections(filtered, detections)

    rows, cols = (0, 0)
    if grid_mode == "2×3":
        rows, cols = 2, 3
    elif grid_mode == "3×3":
        rows, cols = 3, 3
    if rows and cols:
        display = draw_grid_overlay(display, rows, cols)

    tc = frame_timecode(frame_index, fps)
    with main_col:
        st.markdown(f"**Кадр {frame_index}** · `{tc}` · FPS {fps:.2f}")
        if show_original:
            a, b = st.columns(2)
            with a:
                _show_frame(frame, caption="Оригинал")
            with b:
                _show_frame(display, caption="Фильтр / YOLO")
        else:
            _show_frame(display)

        if detections:
            st.caption(
                "YOLO: "
                + ", ".join(f"{d.label} {d.confidence:.2f}" for d in detections[:8])
                + ("…" if len(detections) > 8 else "")
                + " · пустой список ≠ людей нет"
            )
            pick = st.selectbox(
                "BBox → кандидат",
                ["—"] + [f"{i}: {d.label} {d.confidence:.2f}" for i, d in enumerate(detections)],
                key="yolo_pick",
            )
            if pick != "—" and st.button("Взять bbox", key="yolo_use_bbox"):
                idx = int(pick.split(":", 1)[0])
                det = detections[idx]
                st.session_state["candidate_bbox"] = {
                    "x": det.x,
                    "y": det.y,
                    "width": det.width,
                    "height": det.height,
                }
                st.session_state["use_bbox_default"] = True
                st.rerun()
        elif "yolo_detections" in st.session_state:
            st.caption("YOLO: детекций нет на кадре (это не «чисто»).")

        if rows and cols:
            cells = split_grid(filtered, rows, cols)
            focus = st.selectbox("Ячейка крупно", ["—"] + [c[0] for c in cells])
            if focus != "—":
                for label, crop, _box in cells:
                    if label == focus:
                        _show_frame(crop, caption=label)
                        break

    with st.expander("Отметка качества кадра / ячеек", expanded=False):
        segments = segment_repo.list_for_video(video.id)
        cell_status = summarize_cell_statuses(segments, frame_index)
        frame_status = st.selectbox("Статус кадра", [s.value for s in ReviewStatus], key="frame_status")
        frame_issues = st.multiselect("Проблемы", [q.value for q in QualityIssue], key="frame_issues")
        frame_comment = st.text_input("Комментарий", key="frame_comment")
        if st.button("Сохранить статус кадра"):
            if ctrl.session.state != SessionState.ACTIVE:
                st.error("Сначала старт сессии")
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
                st.success("Сохранено")

        if rows and cols:
            cell = st.selectbox("Ячейка", cell_labels(rows, cols))
            st.caption(f"Сейчас: {cell_status.get(cell, ReviewStatus.NOT_REVIEWED).value}")
            cell_st = st.selectbox("Статус ячейки", [s.value for s in ReviewStatus], key="one_cell_st")
            cell_iss = st.multiselect(
                "Проблемы ячейки",
                [q.value for q in QualityIssue],
                key="one_cell_iss",
            )
            if st.button("Сохранить ячейку"):
                if ctrl.session.state != SessionState.ACTIVE:
                    st.error("Сначала старт сессии")
                else:
                    seg = build_segment(
                        video_id=video.id,
                        frame_index=frame_index,
                        fps=fps,
                        grid_cell=cell,
                        review_status=ReviewStatus(cell_st),
                        quality_issues=[QualityIssue(i) for i in cell_iss],
                        operator_id=ctrl.session.id,
                        fatigue_level=ctrl.session.fatigue_warning_level,
                    )
                    segment_repo.create(seg)
                    session_repo.save(ctrl.session)
                    st.success(f"Сохранено: {cell}")

    with st.expander("Кандидат", expanded=False):
        st.caption("Координаты дрона из телеметрии")
        category = st.selectbox("Категория", [c.value for c in CandidateCategory])
        tags = st.multiselect("Evidence tags", [t.value for t in EvidenceTag])
        description = st.text_area("Описание")
        confidence = st.slider("Confidence", 1, 5, 3)
        requires_reflight = st.checkbox("Requires reflight", value=False)
        reflight_reason = st.text_input("Причина reflight") if requires_reflight else None
        use_bbox = st.checkbox(
            "Crop bbox",
            value=bool(st.session_state.get("use_bbox_default", False)),
        )
        bbox: BoundingBox | None = None
        preset = st.session_state.get("candidate_bbox") or {}
        if use_bbox:
            b1, b2, b3, b4 = st.columns(4)
            bx = b1.number_input("x", min_value=0, value=int(preset.get("x", 0)))
            by = b2.number_input("y", min_value=0, value=int(preset.get("y", 0)))
            bw = b3.number_input("w", min_value=1, value=int(preset.get("width", 100)))
            bh = b4.number_input("h", min_value=1, value=int(preset.get("height", 100)))
            bbox = BoundingBox(x=int(bx), y=int(by), width=int(bw), height=int(bh))

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
                    telemetry=(
                        samples[frame_index]
                        if frame_index < len(samples)
                        else (samples[-1] if samples else None)
                    ),
                )
                candidate_repo.create(cand)
                st.success(f"Сохранено: {cand.id}")
            except (ValueError, OSError) as exc:
                st.error(str(exc))

    current_sample = (
        samples[frame_index] if frame_index < len(samples) else (samples[-1] if samples else None)
    )
    return samples, current_sample, frame_index
