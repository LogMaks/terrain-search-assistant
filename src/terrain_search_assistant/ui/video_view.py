"""Video import and selection UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from terrain_search_assistant.domain.enums import IndexingStatus
from terrain_search_assistant.domain.models import SearchOperation, VideoAsset
from terrain_search_assistant.storage.repositories import VideoRepository
from terrain_search_assistant.video.discovery import discover_videos
from terrain_search_assistant.video.metadata import FfprobeError, probe_video


def render_video_view(
    operation: SearchOperation,
    video_repo: VideoRepository,
) -> VideoAsset | None:
    st.subheader("Видео")
    st.caption(
        "Укажите локальный каталог. Многогигабайтные файлы не загружаются через браузер — "
        "сохраняются только путь и метаданные."
    )

    directory = st.text_input("Путь к каталогу с видео", value=st.session_state.get("video_dir", ""))
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
            st.success(f"Импортировано файлов: {len(imported)}")
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
                "SRT": "да" if v.srt_path else "нет",
                "duration_s": v.duration_s,
                "resolution": f"{v.width}x{v.height}" if v.width and v.height else None,
                "fps": v.fps,
                "codec": v.codec,
                "status": v.indexing_status.value,
                "path": v.path,
            }
        )
    st.dataframe(rows, use_container_width=True)

    labels = {v.id: v.filename for v in videos}
    current = st.session_state.get("video_id")
    options = list(labels.keys())
    index = options.index(current) if current in options else 0
    selected = st.selectbox("Активное видео", options=options, format_func=lambda i: labels[i], index=index)
    st.session_state["video_id"] = selected
    video = video_repo.get(selected)
    if video is None:
        return None

    if not Path(video.path).is_file():
        st.error(f"Файл недоступен или перемещён: {video.path}")
        video.indexing_status = IndexingStatus.MISSING_FILE
        video_repo.upsert(video)

    st.caption(f"SRT: {video.srt_path or 'не найден'}")
    return video
