"""Candidates list and review-status updates."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from terrain_search_assistant.config import AppConfig
from terrain_search_assistant.domain.enums import CandidateCategory, ReviewStatus
from terrain_search_assistant.domain.models import SearchOperation
from terrain_search_assistant.storage.repositories import CandidateRepository


def render_candidate_view(
    operation: SearchOperation,
    candidate_repo: CandidateRepository,
    config: AppConfig,
) -> None:
    st.subheader("Кандидаты")
    st.caption("Координаты дрона из телеметрии — не координаты найденного объекта.")
    st.info(
        "Автоматический детектор ещё не подключён.\n"
        "Приложение не делает вывод об отсутствии людей."
    )

    candidates = candidate_repo.list_for_operation(operation.id)
    if not candidates:
        st.write("Пока нет кандидатов")
        return

    cat_filter = st.multiselect(
        "Категория",
        [c.value for c in CandidateCategory],
        default=[],
    )
    status_filter = st.multiselect(
        "Статус",
        [s.value for s in ReviewStatus],
        default=[],
    )
    conf_min, conf_max = st.slider("Confidence", 1, 5, (1, 5))

    filtered = []
    for c in candidates:
        if cat_filter and c.category.value not in cat_filter:
            continue
        if status_filter and c.review_status.value not in status_filter:
            continue
        if not (conf_min <= c.confidence <= conf_max):
            continue
        filtered.append(c)

    st.write(f"Показано: {len(filtered)} / {len(candidates)}")

    for cand in filtered:
        with st.expander(
            f"{cand.category.value} · conf {cand.confidence} · frame {cand.frame_index} · "
            f"{cand.review_status.value}"
        ):
            st.write(cand.description)
            st.write(
                {
                    "id": cand.id,
                    "timestamp_s": cand.timestamp_s,
                    "drone_lat": cand.drone_latitude,
                    "drone_lon": cand.drone_longitude,
                    "tags": [t.value for t in cand.evidence_tags],
                    "requires_reflight": cand.requires_reflight,
                    "reflight_reason": cand.reflight_reason,
                }
            )
            shot = config.data_dir / cand.screenshot_path
            if not shot.is_file():
                # screenshot_path is relative to data/
                alt = Path(cand.screenshot_path)
                shot = alt if alt.is_file() else config.data_dir / cand.screenshot_path
            # artifacts live under data/artifacts; stored path is artifacts/...
            shot = config.data_dir / cand.screenshot_path
            if shot.is_file():
                st.image(str(shot), caption="Screenshot", width=config.preview_width_px)
            else:
                st.caption(f"Screenshot не найден: {shot}")
            if cand.crop_path:
                crop = config.data_dir / cand.crop_path
                if crop.is_file():
                    st.image(
                        str(crop),
                        caption="Crop",
                        width=min(config.preview_width_px, 480),
                    )

            new_status = st.selectbox(
                "Изменить статус",
                [s.value for s in ReviewStatus],
                index=[s.value for s in ReviewStatus].index(cand.review_status.value),
                key=f"cand_status_{cand.id}",
            )
            reflight = st.checkbox(
                "Requires reflight",
                value=cand.requires_reflight,
                key=f"cand_ref_{cand.id}",
            )
            reason = st.text_input(
                "Причина повторного облёта",
                value=cand.reflight_reason or "",
                key=f"cand_reason_{cand.id}",
            )
            if st.button("Обновить статус", key=f"cand_upd_{cand.id}"):
                try:
                    candidate_repo.update_status(
                        cand.id,
                        ReviewStatus(new_status),
                        note="operator update",
                        requires_reflight=reflight,
                        reflight_reason=reason or None,
                    )
                    st.success("Статус обновлён (история сохранена, запись не удалена)")
                    st.rerun()
                except (KeyError, ValueError) as exc:
                    st.error(str(exc))
