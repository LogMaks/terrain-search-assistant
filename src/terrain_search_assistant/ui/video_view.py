"""Video import, separate SRT binding, and track preview."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import streamlit as st

from terrain_search_assistant.config import DEFAULT_CONFIG, AppConfig
from terrain_search_assistant.domain.enums import IndexingStatus
from terrain_search_assistant.domain.models import SearchOperation, VideoAsset
from terrain_search_assistant.storage.repositories import VideoRepository
from terrain_search_assistant.telemetry.dji_srt import SrtParseError, parse_dji_srt_file
from terrain_search_assistant.telemetry.track import (
    list_srt_files,
    load_bound_telemetry,
    track_summary,
)
from terrain_search_assistant.video.discovery import discover_videos, find_matching_srt
from terrain_search_assistant.video.metadata import FfprobeError, probe_video


def _bind_srt(video: VideoAsset, srt_path: Path, video_repo: VideoRepository) -> int:
    samples = parse_dji_srt_file(srt_path)
    video.srt_path = str(srt_path.resolve())
    video_repo.upsert(video)
    summary = track_summary(samples)
    st.session_state[f"track_summary_{video.id}"] = summary
    return len(samples)


def render_video_view(
    operation: SearchOperation,
    video_repo: VideoRepository,
    config: AppConfig | None = None,
) -> VideoAsset | None:
    cfg = config or DEFAULT_CONFIG
    st.subheader("Видео")
    st.caption(
        "Импортируйте видео по пути к каталогу. "
        "SRT необязателен: у части роликов его нет — инспекция всё равно доступна. "
        "Если SRT есть, привяжите его отдельно, и на карте появится трек."
    )

    directory = st.text_input(
        "Путь к каталогу с видео",
        value=st.session_state.get("video_dir", ""),
    )
    recursive = st.checkbox("Рекурсивный поиск", value=False)
    if st.button("Сканировать каталог"):
        if not directory.strip():
            st.error("Укажите путь")
        else:
            try:
                found = discover_videos(Path(directory.strip()), recursive=recursive)
            except FileNotFoundError as exc:
                st.error(str(exc))
                return None
            st.session_state["video_dir"] = directory.strip()
            imported: list[VideoAsset] = []
            for item in found:
                try:
                    meta = probe_video(item.path)
                    status = IndexingStatus.INDEXED
                    err: str | None = None
                except (FfprobeError, FileNotFoundError) as exc:
                    meta = None
                    status = IndexingStatus.ERROR
                    err = str(exc)
                asset = VideoAsset(
                    operation_id=operation.id,
                    path=str(item.path.resolve()),
                    filename=item.path.name,
                    filesize=item.filesize,
                    duration_s=meta.duration_s if meta else None,
                    width=meta.width if meta else None,
                    height=meta.height if meta else None,
                    fps=meta.fps if meta else None,
                    codec=meta.codec if meta else None,
                    srt_path=str(item.srt_path.resolve()) if item.srt_path else None,
                    indexing_status=status,
                    fingerprint=item.fingerprint,
                )
                video_repo.upsert(asset)
                imported.append(asset)
                if err:
                    st.warning(f"{item.path.name}: {err}")
            with_srt = sum(1 for item in found if item.srt_path is not None)
            without_srt = len(imported) - with_srt
            st.success(
                f"Импортировано: {len(imported)} · с SRT: {with_srt} · без SRT: {without_srt}"
            )
            st.rerun()

    videos = video_repo.list_for_operation(operation.id)
    if not videos:
        st.info("Видео ещё не импортированы")
        return None

    rows = []
    for v in videos:
        rows.append(
            {
                "filename": v.filename,
                "SRT": Path(v.srt_path).name if v.srt_path else "нет (это нормально)",
                "duration_s": v.duration_s,
                "resolution": f"{v.width}x{v.height}" if v.width and v.height else None,
                "fps": v.fps,
                "status": v.indexing_status.value,
            }
        )
    st.dataframe(rows, width="stretch")

    labels = {v.id: v.filename for v in videos}
    current = st.session_state.get("video_id")
    options = list(labels.keys())
    index = options.index(current) if current in options else 0
    selected = st.selectbox(
        "Активное видео",
        options=options,
        format_func=lambda i: labels[i],
        index=index,
    )
    st.session_state["video_id"] = selected
    video = video_repo.get(selected)
    if video is None:
        return None

    if not Path(video.path).is_file():
        st.error(f"Файл недоступен или перемещён: {video.path}")
        video.indexing_status = IndexingStatus.MISSING_FILE
        video_repo.upsert(video)

    if not video.srt_path:
        repaired = find_matching_srt(Path(video.path))
        if repaired is not None:
            try:
                n = _bind_srt(video, repaired, video_repo)
            except (SrtParseError, OSError):
                pass
            else:
                st.info(f"Рядом найден SRT `{repaired.name}` · семплов: {n}")

    st.markdown("### SRT (опционально)")
    st.caption(
        "Не у всех видео есть SRT — это штатная ситуация. "
        "Без SRT можно проверять кадры; трек и координаты дрона будут недоступны. "
        "Если файл телеметрии всё же есть (даже с другим именем) — привяжите ниже."
    )
    if video.srt_path:
        st.write(f"Текущий SRT: `{video.srt_path}`")
    else:
        st.info("У этого видео нет SRT. Можно продолжать инспекцию без трека.")

    bind_cols = st.columns(2)
    with bind_cols[0]:
        manual_srt = st.text_input(
            "Путь к SRT-файлу",
            value=video.srt_path or "",
            key=f"manual_srt_{video.id}",
        )
        c1, c2 = st.columns(2)
        if c1.button("Привязать SRT", type="primary", key=f"bind_srt_{video.id}"):
            srt_path = Path(manual_srt.strip()) if manual_srt.strip() else None
            if srt_path is None or not srt_path.is_file():
                st.error("SRT-файл не найден")
            elif srt_path.suffix.lower() != ".srt":
                st.error("Нужен файл .srt / .SRT")
            else:
                try:
                    n = _bind_srt(video, srt_path, video_repo)
                except (SrtParseError, OSError) as exc:
                    st.error(f"Не удалось прочитать SRT: {exc}")
                else:
                    st.success(f"SRT привязан · семплов: {n}")
                    st.rerun()
        if c2.button("Отвязать SRT", key=f"unbind_srt_{video.id}"):
            video.srt_path = None
            video_repo.upsert(video)
            st.session_state.pop(f"track_summary_{video.id}", None)
            st.rerun()

    with bind_cols[1]:
        srt_dir = st.text_input(
            "Каталог для поиска SRT",
            value=st.session_state.get("srt_dir", st.session_state.get("video_dir", "")),
            key=f"srt_dir_{video.id}",
        )
        srt_recursive = st.checkbox("Рекурсивно", value=False, key=f"srt_rec_{video.id}")
        if st.button("Найти SRT в каталоге", key=f"scan_srt_{video.id}"):
            if not srt_dir.strip():
                st.error("Укажите каталог")
            else:
                try:
                    found_srt = list_srt_files(Path(srt_dir.strip()), recursive=srt_recursive)
                except FileNotFoundError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["srt_dir"] = srt_dir.strip()
                    st.session_state[f"srt_candidates_{video.id}"] = [str(p) for p in found_srt]
                    st.success(f"Найдено SRT: {len(found_srt)}")

        candidates = st.session_state.get(f"srt_candidates_{video.id}", [])
        if candidates:
            choice = st.selectbox(
                "Выберите SRT",
                options=candidates,
                format_func=lambda p: Path(p).name,
                key=f"srt_choice_{video.id}",
            )
            if st.button("Привязать выбранный SRT", key=f"bind_choice_{video.id}"):
                try:
                    n = _bind_srt(video, Path(choice), video_repo)
                except (SrtParseError, OSError) as exc:
                    st.error(f"Не удалось прочитать SRT: {exc}")
                else:
                    st.success(f"SRT привязан · семплов: {n}")
                    st.rerun()

    st.markdown("### Трек активного видео")
    samples, err = load_bound_telemetry(video, config=cfg)
    if err == "SRT не привязан к видео":
        st.caption("Трек недоступен: у ролика нет привязанного SRT.")
    elif err:
        st.warning(err)
    else:
        summary = track_summary(samples)
        st.session_state[f"track_summary_{video.id}"] = summary
        samples_total = cast(int, summary["samples_total"])
        gps_points = cast(int, summary["gps_points"])
        has_track = cast(bool, summary["has_track"])
        m1, m2, m3 = st.columns(3)
        m1.metric("Семплов SRT", samples_total)
        m2.metric("Точек GPS", gps_points)
        m3.metric("Трек готов", "да" if has_track else "нет")
        if has_track:
            st.success(
                "Трек построен по привязанному SRT. Откройте вкладку «Карта», "
                "чтобы увидеть маршрут старт → финиш."
            )
            st.caption(f"Старт: {summary['start']} · Финиш: {summary['end']}")
        else:
            st.caption(
                "В SRT меньше двух GPS-точек — линию маршрута построить нельзя."
            )

    return video
