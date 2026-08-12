"""Operation management UI."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from terrain_search_assistant.domain.enums import OperationStatus
from terrain_search_assistant.domain.models import SearchOperation
from terrain_search_assistant.geo.area import format_area
from terrain_search_assistant.geo.sectors import summarize_sectors
from terrain_search_assistant.storage.repositories import (
    CandidateRepository,
    OperationRepository,
    SectorRepository,
    VideoRepository,
)


def render_operation_view(
    op_repo: OperationRepository,
    sector_repo: SectorRepository,
    video_repo: VideoRepository,
    candidate_repo: CandidateRepository,
) -> SearchOperation | None:
    st.subheader("Операция поиска")
    st.info(
        "Автоматический детектор ещё не подключён.\n"
        "Приложение не делает вывод об отсутствии людей."
    )

    operations = op_repo.list_all()
    with st.expander("Создать операцию", expanded=not operations):
        name = st.text_input("Название операции")
        comment = st.text_area("Комментарий", value="")
        if st.button("Создать", type="primary"):
            if not name.strip():
                st.error("Укажите название")
            else:
                now = datetime.now(UTC)
                op = SearchOperation(
                    name=name.strip(),
                    created_at=now,
                    updated_at=now,
                    status=OperationStatus.ACTIVE,
                    comment=comment.strip() or None,
                )
                op_repo.create(op)
                st.session_state["operation_id"] = op.id
                st.success(f"Операция создана: {op.name}")
                st.rerun()

    if not operations:
        st.warning("Создайте первую операцию")
        return None

    labels = {o.id: f"{o.name} [{o.status.value}]" for o in operations}
    current = st.session_state.get("operation_id", operations[0].id)
    if current not in labels:
        current = operations[0].id
    selected_id = st.selectbox(
        "Активная операция",
        options=list(labels.keys()),
        format_func=lambda i: labels[i],
        index=list(labels.keys()).index(current),
    )
    st.session_state["operation_id"] = selected_id
    operation = op_repo.get(selected_id)
    if operation is None:
        st.error("Операция не найдена")
        return None

    col1, col2 = st.columns(2)
    with col1:
        new_status = st.selectbox(
            "Статус",
            options=[s.value for s in OperationStatus],
            index=[s.value for s in OperationStatus].index(operation.status.value),
        )
    with col2:
        new_comment = st.text_area("Комментарий операции", value=operation.comment or "")

    if st.button("Сохранить изменения операции"):
        operation.status = OperationStatus(new_status)
        operation.comment = new_comment.strip() or None
        operation.updated_at = datetime.now(UTC)
        op_repo.update(operation)
        st.success("Сохранено")
        st.rerun()

    sectors = sector_repo.list_for_operation(operation.id)
    videos = video_repo.list_for_operation(operation.id)
    candidates = candidate_repo.count_for_operation(operation.id)
    summary = summarize_sectors(sectors)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Секторы", len(sectors))
    m2.metric("Видео", len(videos))
    m3.metric("Кандидаты", candidates)
    area = format_area(summary.union_m2)
    m4.metric("Площадь объединения", f"{area['ha']:.2f} га")

    st.caption(
        f"Сумма площадей секторов: {format_area(summary.sum_individual_m2)['ha']:.2f} га · "
        f"перекрытие: {format_area(summary.overlap_m2)['ha']:.2f} га "
        f"({summary.overlap_ratio:.0%})"
    )
    if summary.has_substantial_overlap:
        st.warning("Существенное перекрытие секторов — общая площадь считается по объединению.")

    return operation
