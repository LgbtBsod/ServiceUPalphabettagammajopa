#!/usr/bin/env python3

"""Тесты для сортировки по колонкам в таблицах заказов — раньше только
"Цена" сортировалась численно, "Заказ №"/"Дней" (числовые, но текстовые
колонки Treeview) и обе колонки дат сортировались как обычные строки:
"1"/"10"/"11"/"2" по алфавиту, дата — по дню месяца в начале строки,
игнорируя месяц/год (найдено design-review workflow'ом). Методы — чистые
@staticmethod, тестируются без поднятия Tk."""

from __future__ import annotations

from datetime import datetime

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from gui.dialogs.client_history import ClientHistoryWindow
from gui.main_window_parts.devices_table_mixin import DevicesTableMixin


class TestDevicesTableSortKeys:
    def test_int_sort_key_orders_numerically_not_lexicographically(self):
        values = ["2", "10", "1", "20", "11"]
        ordered = sorted(values, key=DevicesTableMixin._int_sort_key)
        assert ordered == ["1", "2", "10", "11", "20"]

    def test_int_sort_key_non_numeric_falls_back_to_zero(self):
        assert DevicesTableMixin._int_sort_key("—") == 0
        assert DevicesTableMixin._int_sort_key("") == 0

    def test_price_sort_key_strips_currency_and_spaces(self):
        assert DevicesTableMixin._price_sort_key("1 500 ₽") == 1500.0
        assert DevicesTableMixin._price_sort_key("") == 0.0

    def test_date_sort_key_orders_by_real_date_not_leading_digit(self):
        # Лексикографически "02.01.2026" < "15.01.2025" (день '0' < '1') —
        # по факту 2025 год раньше 2026.
        values = ["15.01.2025", "02.01.2026", "01.01.2020"]
        ordered = sorted(values, key=DevicesTableMixin._date_sort_key)
        assert ordered == ["01.01.2020", "15.01.2025", "02.01.2026"]

    def test_date_sort_key_handles_date_with_time(self):
        assert DevicesTableMixin._date_sort_key("01.01.2026 15:30") == datetime(
            2026, 1, 1, 15, 30
        )

    def test_date_sort_key_empty_or_dash_goes_first(self):
        assert DevicesTableMixin._date_sort_key("") == datetime.min
        assert DevicesTableMixin._date_sort_key("—") == datetime.min

    def test_date_sort_key_unparsable_does_not_raise(self):
        assert DevicesTableMixin._date_sort_key("не дата") == datetime.min


class TestClientHistorySortKeys:
    def test_date_sort_key_orders_by_real_date(self):
        values = ["15.01.2025", "02.01.2026", "01.01.2020"]
        ordered = sorted(values, key=ClientHistoryWindow._safe_date_sort_key)
        assert ordered == ["01.01.2020", "15.01.2025", "02.01.2026"]

    def test_date_sort_key_empty_goes_first(self):
        assert ClientHistoryWindow._safe_date_sort_key("") == datetime.min
