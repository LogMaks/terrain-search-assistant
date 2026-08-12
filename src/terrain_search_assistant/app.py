"""Streamlit entrypoint for Terrain Search Assistant."""

from __future__ import annotations

import streamlit as st

from terrain_search_assistant.config import DEFAULT_CONFIG
from terrain_search_assistant.domain.models import TelemetrySample
from terrain_search_assistant.storage.database import Database
from terrain_search_assistant.storage.repositories import (
    CandidateRepository,
    OperationRepository,
    SectorRepository,
    SegmentRepository,
    SessionRepository,
    VideoRepository,
)
from terrain_search_assistant.ui.candidate_view import render_candidate_view
from terrain_search_assistant.ui.map_view import render_map_view
from terrain_search_assistant.ui.operation_view import render_operation_view
from terrain_search_assistant.ui.review_view import render_review_view
from terrain_search_assistant.ui.video_view import render_video_view


def main() -> None:
    st.set_page_config(
        page_title="Terrain Search Assistant",
        page_icon="🛫",
        layout="wide",
    )
    st.title("Terrain Search Assistant")
    st.caption(
        "Локальное средство поддержки оператора. "
        "Не делает вывод «людей нет» и не заявляет точное покрытие без DEM."
    )

    config = DEFAULT_CONFIG
    config.ensure_dirs()
    db = Database(config.db_path)

    op_repo = OperationRepository(db)
    sector_repo = SectorRepository(db)
    video_repo = VideoRepository(db)
    session_repo = SessionRepository(db)
    segment_repo = SegmentRepository(db)
    candidate_repo = CandidateRepository(db)

    tab_op, tab_video, tab_review, tab_map, tab_cand = st.tabs(
        ["Операция", "Видео", "Инспекция", "Карта", "Кандидаты"]
    )

    with tab_op:
        operation = render_operation_view(op_repo, sector_repo, video_repo, candidate_repo)

    if operation is None:
        with tab_video:
            st.info("Сначала создайте или выберите операцию")
        with tab_review:
            st.info("Сначала создайте или выберите операцию")
        with tab_map:
            st.info("Сначала создайте или выберите операцию")
        with tab_cand:
            st.info("Сначала создайте или выберите операцию")
        return

    with tab_video:
        video = render_video_view(operation, video_repo)

    samples: list[TelemetrySample] = []
    current_sample: TelemetrySample | None = None
    with tab_review:
        if video is None:
            st.info("Импортируйте и выберите видео")
        else:
            samples, current_sample, _frame_idx = render_review_view(
                operation,
                video,
                session_repo,
                segment_repo,
                candidate_repo,
                config,
            )

    with tab_map:
        render_map_view(operation, sector_repo, samples, current_sample, config)

    with tab_cand:
        render_candidate_view(operation, candidate_repo, config)


if __name__ == "__main__":
    main()
