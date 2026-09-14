"""Flet-оболочка ServiceUP: тема, навигация, переключение вью.

Второй, равноправный фронт поверх ТОГО ЖЕ ядра (core.kernel), что и
классический customtkinter-интерфейс (gui/) — см. gui/dialogs/ui_chooser.py.
Не PWA (pwa/server.py, урезанный мобильный API) — здесь полный доступ к
Database через core.get_db_access(), как у gui/main_window.py.

Сознательно НЕ полный паритет с customtkinter-интерфейсом с первого дня:
покрыты Баланс/Дашборд, Заказы (список, создание, редактирование, смена
статуса, поиск, фильтр по статусу, печать актов), Макет акта (свободный
canvas-билдер + импорт из файла — views_act_builder.py), Справочники
(бренды/типы устройств/модели/инженеры и т.д. — views_dictionaries.py) и
Настройки (тема, апдейтер). Фото к заказам и сотрудники — пока только в
классическом интерфейсе (gui/); использовать его для этих задач.
"""

from __future__ import annotations

import logging

import flet as ft

from . import theme
from .views_act_builder import ActBuilderView
from .views_dictionaries import DictionariesView
from .views_orders import OrdersView
from .views_settings import DashboardView, SettingsView

log = logging.getLogger(__name__)

_NAV: list[tuple[str, str, object, object]] = [
    ("dashboard", "Дашборд", ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD),
    ("orders", "Заказы", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
    ("act_builder", "Макет акта", ft.Icons.DESIGN_SERVICES_OUTLINED, ft.Icons.DESIGN_SERVICES),
    ("dictionaries", "Справочники", ft.Icons.MENU_BOOK_OUTLINED, ft.Icons.MENU_BOOK),
    ("settings", "Настройки", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS),
]


class ServiceApp:
    """Данные (db/settings/APIs ядра) общие на процесс; page/вью — на сессию
    браузера (несколько вкладок могут смотреть на одно и то же ядро)."""

    def __init__(self, core):
        self.core = core
        self.db = core.get_db_access()
        self.settings_api = core.get_module_api("settings")
        self.page: ft.Page | None = None
        self.current_view = "dashboard"
        self._views: dict[str, object] = {}
        self._rail: ft.NavigationRail | None = None
        self._host: ft.Container | None = None
        self._scroll: ft.Column | None = None
        self._divider: ft.VerticalDivider | None = None
        # Путь последнего temp-PDF, созданного views_orders.py::_print_act()
        # — удаляется перед созданием следующего, чтобы печать не копила
        # осиротевшие файлы (см. комментарий в _print_act()).
        self._last_act_print_path: str | None = None

    # ── lifecycle ─────────────────────────────────────────────

    def main(self, page: ft.Page) -> None:
        self.page = page
        page.title = "ServiceUP"
        page.padding = 0
        self._apply_theme()

        self._views = {
            "dashboard": DashboardView(self),
            "orders": OrdersView(self),
            "act_builder": ActBuilderView(self),
            "dictionaries": DictionariesView(self),
            "settings": SettingsView(self),
        }

        self._rail = ft.NavigationRail(
            selected_index=1,  # Заказы — самый частый экран
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=76,
            min_extended_width=204,
            extended=True,
            group_alignment=-0.95,
            bgcolor="transparent",
            leading=self._build_rail_leading(),
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icon(off), selected_icon=ft.Icon(on), label=label)
                for _key, label, off, on in _NAV
            ],
            on_change=self._on_nav_change,
        )
        self._divider = ft.VerticalDivider(width=1, color=self.colors["border"])

        self._scroll = ft.Column([], expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)
        self._host = ft.Container(self._scroll, expand=True,
                                   padding=ft.Padding(28, 24, 28, 24), bgcolor=self.colors["bg_primary"])
        page.add(
            ft.Row(
                [self._rail, self._divider, self._host],
                expand=True, spacing=0,
            )
        )
        self.navigate("orders")

    def _build_rail_leading(self) -> ft.Container:
        return ft.Container(
            ft.Row(
                [ft.Icon(ft.Icons.BUILD_CIRCLE_ROUNDED, color=self.colors["accent"], size=22),
                 ft.Text("ServiceUP", weight=ft.FontWeight.W_700, size=15,
                         color=self.colors["text_primary"])],
                spacing=10,
            ),
            padding=ft.Padding(16, 18, 8, 18),
        )

    def _apply_theme(self) -> None:
        page = self.page
        mode = self.settings_api.get("theme", "light")
        self.colors = theme.colors(mode, self.settings_api.get("accent_color", "#0078d4"))
        page.theme = theme.build_theme(dark=False)
        page.dark_theme = theme.build_theme(dark=True)
        page.theme_mode = ft.ThemeMode.DARK if mode == "dark" else ft.ThemeMode.LIGHT
        page.bgcolor = self.colors["bg_primary"]

    def set_theme_mode(self, mode: str) -> None:
        self.settings_api.set("theme", mode)
        self._apply_theme()
        if self._host is not None:
            self._host.bgcolor = self.colors["bg_primary"]
        # rerender() ниже перерисовывает только self._scroll (текущее вью) —
        # self._rail строится ОДИН раз в main() с цветами, зафиксированными
        # на момент запуска, и никогда не трогается заново; тот же случай с
        # self._divider. Без этого переключение темы перекрашивало фон и
        # текущее вью, но лого/название "ServiceUP" в навигации и разделитель
        # оставались в цветах старой темы (workflow-найденный баг).
        if self._rail is not None:
            self._rail.leading = self._build_rail_leading()
        if self._divider is not None:
            self._divider.color = self.colors["border"]
        self.rerender()
        self.page.update()

    # ── navigation ───────────────────────────────────────────

    def _on_nav_change(self, e: ft.ControlEvent) -> None:
        idx = e.control.selected_index
        if 0 <= idx < len(_NAV):
            self.navigate(_NAV[idx][0])

    def navigate(self, key: str) -> None:
        self.current_view = key
        self._scroll = ft.Column([self._views[key].render()], expand=True, scroll=ft.ScrollMode.AUTO)
        self._host.content = self._scroll
        if self._rail is not None:
            self._rail.selected_index = next((i for i, n in enumerate(_NAV) if n[0] == key), 0)
        self.page.update()

    def rerender(self) -> None:
        self._scroll.controls = [self._views[self.current_view].render()]
        self.page.update()

    # ── helpers ──────────────────────────────────────────────

    def show_snackbar(self, message: str, *, error: bool = False) -> None:
        # page.open() не существует в этой версии Flet — show_dialog() и
        # рендерит SnackBar точно так же (тот же API, что и в finance_calculator).
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                bgcolor=self.colors["error"] if error else self.colors["success"],
                duration=3000,
            )
        )


def run_app(core, port: int = 8421) -> None:
    """Точка входа Flet-оболочки (локальный web-сервер + вкладка браузера).

    ``core`` — уже инициализированное ядро (bootstrap.initialize_kernel()),
    то же самое, что использует customtkinter-интерфейс — обе оболочки
    читают/пишут одну и ту же БД в реальном времени."""

    def session_main(page: ft.Page) -> None:
        ServiceApp(core).main(page)

    ft.run(
        session_main,
        view=ft.AppView.WEB_BROWSER,
        port=port,
        web_renderer=ft.WebRenderer.CANVAS_KIT,
    )
