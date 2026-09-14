"""Дашборд и настройки Flet-оболочки."""

from __future__ import annotations

import asyncio

import flet as ft

from . import theme


class DashboardView:
    def __init__(self, app):
        self.app = app

    def render(self) -> ft.Control:
        c = self.app.colors
        stats = self.app.db.get_statistics()

        def stat_card(title: str, value: str, color: str) -> ft.Container:
            return ft.Container(
                ft.Column(
                    [
                        ft.Text(title, size=13, color=c["text_secondary"]),
                        ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=color),
                    ],
                    spacing=4,
                ),
                bgcolor=c["bg_card"], border_radius=12, padding=20, expand=True,
                border=theme.card_border(c["border"]),
            )

        return ft.Column(
            [
                ft.Text("Дашборд", size=24, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                ft.Container(height=8),
                ft.ResponsiveRow(
                    [
                        ft.Container(stat_card("Всего заказов", str(stats["total"]), c["accent"]),
                                     col={"sm": 12, "md": 6, "lg": 3}),
                        ft.Container(stat_card("В работе", str(stats["in_repair"]), c["warning"]),
                                     col={"sm": 12, "md": 6, "lg": 3}),
                        ft.Container(stat_card("Готово к выдаче", str(stats["ready"]), c["success"]),
                                     col={"sm": 12, "md": 6, "lg": 3}),
                        ft.Container(
                            stat_card("Доход (выдано)", f"{stats['total_income']:,.0f} ₽".replace(",", " "),
                                      c["accent"]),
                            col={"sm": 12, "md": 6, "lg": 3},
                        ),
                    ],
                    spacing=16, run_spacing=16,
                ),
            ],
            spacing=8,
        )


class SettingsView:
    def __init__(self, app):
        self.app = app

    def render(self) -> ft.Control:
        c = self.app.colors
        current_theme = self.app.settings_api.get("theme", "light")

        from config.settings import get_version

        def on_theme_change(e: ft.ControlEvent) -> None:
            # SegmentedButton.selected — list[str], не set (set не
            # сериализуется в msgpack при передаче контрола обратно клиенту).
            mode = e.control.selected[0] if e.control.selected else "light"
            self.app.set_theme_mode(mode)

        theme_selector = ft.SegmentedButton(
            selected=[current_theme],
            segments=[
                ft.Segment(value="light", label=ft.Text("Светлая")),
                ft.Segment(value="dark", label=ft.Text("Тёмная")),
            ],
            on_change=on_theme_change,
        )

        status_text = ft.Text("", size=12, color=c["text_secondary"])

        def check_updates(_e) -> None:
            status_text.value = "Проверка..."
            self.app.page.update()

            async def _check() -> None:
                from utils.update_manager import check_updates_at_startup

                result = await asyncio.to_thread(check_updates_at_startup)
                if result.get("error"):
                    status_text.value = f"Ошибка: {result['error']}"
                elif result.get("has_update"):
                    status_text.value = f"Доступна версия {result['latest_version']} — установите через классический интерфейс."
                else:
                    status_text.value = "У вас последняя версия."
                self.app.page.update()

            self.app.page.run_task(_check)

        return ft.Column(
            [
                ft.Text("Настройки", size=24, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                ft.Container(height=12),
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("Оформление", size=14, weight=ft.FontWeight.W_600,
                                    color=c["text_primary"]),
                            ft.Container(height=8),
                            theme_selector,
                        ],
                    ),
                    bgcolor=c["bg_card"], border_radius=12, padding=20,
                    border=theme.card_border(c["border"]),
                ),
                ft.Container(height=16),
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("Обновления", size=14, weight=ft.FontWeight.W_600,
                                    color=c["text_primary"]),
                            ft.Text(f"Текущая версия: {get_version()}", size=12,
                                    color=c["text_secondary"]),
                            ft.Container(height=8),
                            ft.OutlinedButton("Проверить обновления", on_click=check_updates),
                            status_text,
                        ],
                    ),
                    bgcolor=c["bg_card"], border_radius=12, padding=20,
                    border=theme.card_border(c["border"]),
                ),
                ft.Container(height=16),
                ft.Container(
                    ft.Text(
                        "Фото к заказам и сотрудники пока доступны только в "
                        "классическом интерфейсе — переключитесь на него из окна "
                        "выбора при следующем запуске.",
                        size=12, color=c["text_secondary"],
                    ),
                    bgcolor=c["bg_card"], border_radius=12, padding=20,
                    border=theme.card_border(c["border"]),
                ),
            ],
            spacing=0,
        )
