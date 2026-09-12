"""Тесты чистой логики Flet-оболочки (gui_flet/) — без поднятия страницы.

customtkinter-интерфейс (gui/) тоже не покрыт юнит-тестами (виджеты Tk
нельзя осмысленно тестировать headless) — здесь то же самое ограничение для
Control-дерева Flet. Но часть логики вокруг вью — чистые функции, не
требующие Page/сессии, и именно на этой границе уже случались реальные
регрессии (Dropdown.Option без text — молча пустая подпись в браузере,
найдено только живым прогоном), поэтому стоит закрепить их тестами."""

from __future__ import annotations

from domain.constants import STATUSES
from gui_flet.theme import card_border, colors
from gui_flet.views_orders import _opt, _status_options


class TestDropdownOption:
    def test_opt_sets_both_key_and_text(self):
        opt = _opt("В работе")
        assert opt.key == "В работе"
        assert opt.text == "В работе"

    def test_opt_custom_label(self):
        opt = _opt("Готов", label="Готов (устаревший статус)")
        assert opt.key == "Готов"
        assert opt.text == "Готов (устаревший статус)"

    def test_opt_empty_value_falls_back_to_dash(self):
        opt = _opt("")
        assert opt.text == "—"


class TestStatusOptions:
    def test_known_status_not_duplicated(self):
        opts = _status_options(STATUSES[0])
        keys = [o.key for o in opts]
        assert keys.count(STATUSES[0]) == 1
        assert keys == list(STATUSES)

    def test_legacy_status_prepended(self):
        opts = _status_options("Готов")
        assert opts[0].key == "Готов"
        assert "устаревш" in opts[0].text
        # Остальные штатные статусы всё ещё присутствуют — легаси-значение
        # не замещает список, а дополняет его.
        assert [o.key for o in opts[1:]] == list(STATUSES)

    def test_empty_status_no_extra_option(self):
        opts = _status_options("")
        assert [o.key for o in opts] == list(STATUSES)


class TestTheme:
    def test_colors_light_and_dark_have_same_keys(self):
        light = colors("light")
        dark = colors("dark")
        assert set(light.keys()) == set(dark.keys())
        assert "bg_card" in light and "text_primary" in light

    def test_card_border_uses_same_color_all_sides(self):
        border = card_border("#d2d2d7")
        assert border.top.color == "#d2d2d7"
        assert border.left.color == border.right.color == border.bottom.color == border.top.color
