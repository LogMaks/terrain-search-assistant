"""Map UI: sectors, track, approximate visir."""

from __future__ import annotations

from typing import Any

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from terrain_search_assistant.config import AppConfig
from terrain_search_assistant.domain.enums import SectorPriority, SectorStatus
from terrain_search_assistant.domain.models import SearchOperation, SearchSector, TelemetrySample
from terrain_search_assistant.geo.area import format_area
from terrain_search_assistant.geo.bearing import build_visir_line, telemetry_track_linestring
from terrain_search_assistant.geo.sectors import (
    SectorGeometryError,
    compute_sector_area_m2,
    summarize_sectors,
    validate_sector_geojson,
)
from terrain_search_assistant.storage.repositories import SectorRepository


def _default_center(samples: list[TelemetrySample], sectors: list[SearchSector]) -> tuple[float, float]:
    for s in samples:
        if s.latitude is not None and s.longitude is not None:
            return s.latitude, s.longitude
    for sector in sectors:
        geom = sector.geometry
        coords = geom.get("coordinates")
        if geom.get("type") == "Polygon" and coords:
            lon, lat = coords[0][0][:2]
            return float(lat), float(lon)
    return 46.0, 7.0  # generic alpine fallback for empty map only


def render_map_view(
    operation: SearchOperation,
    sector_repo: SectorRepository,
    samples: list[TelemetrySample],
    current_sample: TelemetrySample | None,
    config: AppConfig,
    *,
    video_label: str | None = None,
) -> None:
    st.subheader("Карта")
    st.caption(
        "Ориентировочный визир.\n"
        "Пересечение с рельефом ещё не рассчитано."
    )
    if video_label:
        gps_n = sum(
            1 for s in samples if s.latitude is not None and s.longitude is not None
        )
        st.caption(f"Видео: **{video_label}** · точек GPS в треке: {gps_n}")
    if not samples:
        st.caption(
            "Трек не показан: у активного видео нет SRT (это нормально). "
            "Секторы и карта по-прежнему доступны."
        )

    sectors = sector_repo.list_for_operation(operation.id)
    center = _default_center(samples, sectors)
    fmap = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

    # Track
    points = [
        (s.longitude, s.latitude)
        for s in samples
        if s.longitude is not None and s.latitude is not None
    ]
    line = telemetry_track_linestring([(float(lon), float(lat)) for lon, lat in points])
    if line is not None:
        folium.GeoJson(line, name="Маршрут дрона", style_function=lambda _: {"color": "#1f77b4"}).add_to(
            fmap
        )
        start = points[0]
        end = points[-1]
        folium.Marker([start[1], start[0]], tooltip="Старт", icon=folium.Icon(color="green")).add_to(fmap)
        folium.Marker([end[1], end[0]], tooltip="Финиш", icon=folium.Icon(color="red")).add_to(fmap)

    # Current drone position + visir
    if current_sample and current_sample.latitude is not None and current_sample.longitude is not None:
        folium.CircleMarker(
            [current_sample.latitude, current_sample.longitude],
            radius=6,
            color="#d62728",
            fill=True,
            tooltip="Текущее положение дрона",
        ).add_to(fmap)
        if current_sample.gimbal_yaw is None:
            st.info("Визир не построен: отсутствует gimbal_yaw в телеметрии.")
        else:
            visir = build_visir_line(
                current_sample.longitude,
                current_sample.latitude,
                current_sample.gimbal_yaw,
                length_m=config.default_visir_length_m,
            )
            folium.PolyLine(  # type: ignore[no-untyped-call]
                [[visir.start_lat, visir.start_lon], [visir.end_lat, visir.end_lon]],
                color="#ff7f0e",
                weight=3,
                tooltip="Ориентировочный визир",
            ).add_to(fmap)

        with st.expander("Телеметрия текущего кадра", expanded=False):
            st.write(
                {
                    "timestamp": str(current_sample.timestamp) if current_sample.timestamp else None,
                    "altitude_rel": current_sample.relative_altitude,
                    "altitude_abs": current_sample.absolute_altitude,
                    "yaw": current_sample.gimbal_yaw,
                    "pitch": current_sample.gimbal_pitch,
                    "focal_length": current_sample.focal_length,
                    "zoom": current_sample.digital_zoom,
                    "примечание": "Координаты дрона из телеметрии — не координаты объекта",
                }
            )

    for sector in sectors:
        folium.GeoJson(
            sector.geometry,
            name=sector.name,
            tooltip=f"{sector.name} · {format_area(sector.area_m2)['ha']:.2f} га",
            style_function=lambda _: {"color": "#2ca02c", "fillOpacity": 0.2},
        ).add_to(fmap)

    Draw(  # type: ignore[no-untyped-call]
        export=False,
        draw_options={
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polygon": True,
            "rectangle": True,
        },
    ).add_to(fmap)
    folium.LayerControl().add_to(fmap)

    map_state = st_folium(fmap, width=None, height=520, key=f"map_{operation.id}")

    st.markdown("### Секторы")
    drawn = _extract_drawn_geometry(map_state)
    with st.form("save_sector"):
        name = st.text_input("Имя сектора", value=f"Сектор {len(sectors) + 1}")
        priority = st.selectbox("Приоритет", [p.value for p in SectorPriority], index=1)
        status = st.selectbox("Статус", [s.value for s in SectorStatus], index=0)
        comment = st.text_input("Комментарий", value="")
        submitted = st.form_submit_button("Сохранить нарисованный сектор")
        if submitted:
            if drawn is None:
                st.error("Нарисуйте Polygon или Rectangle на карте")
            else:
                try:
                    geom = validate_sector_geojson(drawn)
                    area = compute_sector_area_m2(geom)
                    sector = SearchSector(
                        operation_id=operation.id,
                        name=name.strip() or "Сектор",
                        priority=SectorPriority(priority),
                        status=SectorStatus(status),
                        geometry=geom,
                        area_m2=area,
                        comment=comment.strip() or None,
                    )
                    sector_repo.create(sector)
                    st.success(
                        f"Сектор сохранён · площадь {format_area(area)['m2']:.0f} м² "
                        f"/ {format_area(area)['ha']:.3f} га / {format_area(area)['km2']:.5f} км²"
                    )
                    st.rerun()
                except SectorGeometryError as exc:
                    st.error(str(exc))

    if sectors:
        summary = summarize_sectors(sectors, overlap_warning_ratio=config.overlap_warning_ratio)
        st.write(
            {
                "сумма_площадей_м2": round(summary.sum_individual_m2, 1),
                "объединение_м2": round(summary.union_m2, 1),
                "перекрытие_м2": round(summary.overlap_m2, 1),
                "доля_перекрытия": round(summary.overlap_ratio, 3),
            }
        )
        if summary.has_substantial_overlap:
            st.warning("Существенное перекрытие секторов.")

        for sector in sectors:
            cols = st.columns([4, 1])
            cols[0].write(
                f"**{sector.name}** · {sector.priority.value} · {sector.status.value} · "
                f"{format_area(sector.area_m2)['ha']:.3f} га"
            )
            if cols[1].button("Удалить", key=f"del_{sector.id}"):
                st.session_state["pending_delete_sector"] = sector.id

        pending = st.session_state.get("pending_delete_sector")
        if pending:
            st.error("Подтвердите удаление выбранного сектора")
            c1, c2 = st.columns(2)
            if c1.button("Подтвердить удаление"):
                sector_repo.delete(pending)
                st.session_state.pop("pending_delete_sector", None)
                st.rerun()
            if c2.button("Отмена"):
                st.session_state.pop("pending_delete_sector", None)
                st.rerun()

    st.markdown(
        """
**Легенда**
- синий — маршрут дрона
- красный маркер — текущее положение
- оранжевый — ориентировочный визир (без пересечения с DEM)
- зелёный — секторы поиска
"""
    )


def _extract_drawn_geometry(map_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not map_state:
        return None
    last = map_state.get("last_active_drawing")
    if isinstance(last, dict) and last.get("geometry"):
        geom = last["geometry"]
        return geom if isinstance(geom, dict) else None
    all_drawings = map_state.get("all_drawings")
    if isinstance(all_drawings, dict):
        features = all_drawings.get("features") or []
        if features:
            geom = features[-1].get("geometry")
            return geom if isinstance(geom, dict) else None
    if isinstance(all_drawings, list) and all_drawings:
        last_feature = all_drawings[-1]
        if isinstance(last_feature, dict) and last_feature.get("geometry"):
            geom = last_feature["geometry"]
            return geom if isinstance(geom, dict) else None
    return None
