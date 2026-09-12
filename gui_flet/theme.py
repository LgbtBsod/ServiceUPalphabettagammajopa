"""Цветовая палитра Flet-оболочки — та же macOS-схема, что и в
utils/colors.py (классический интерфейс), чтобы обе оболочки выглядели
согласованно, а не как два разных продукта."""

from __future__ import annotations

import flet as ft

from utils.colors import get_colors


def colors(theme: str = "light", accent: str = "#0078d4") -> dict[str, str]:
    return get_colors(theme, accent)


def build_theme(dark: bool) -> ft.Theme:
    return ft.Theme(
        color_scheme_seed="#0078d4",
        use_material3=True,
        visual_density=ft.VisualDensity.COMPACT,
    )


def card_border(color: str, width: int = 1) -> ft.Border:
    """ft.border.all() в этой версии Flet не существует — Border/BorderSide
    собираются вручную (см. dataclasses.fields(ft.Border) -> top/right/bottom/left)."""
    side = ft.BorderSide(width=width, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


STATUS_COLORS = {
    "Диагностика": "#8e8e93",
    "Ожидание запчастей": "#ff9f0a",
    "В ремонте": "#007aff",
    "Готов к выдаче": "#34c759",
    "Выдан клиенту": "#8e8e93",
    "Отказ от ремонта": "#ff3b30",
}

PRIORITY_COLORS = {
    "Низкий": "#8e8e93",
    "Обычный": "#007aff",
    "Высокий": "#ff9f0a",
    "Срочный": "#ff3b30",
}
